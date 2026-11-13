package auth

import (
	"context"
	"crypto/hmac"
	"crypto/rand"
	"crypto/sha256"
	"database/sql"
	"encoding/base64"
	"errors"
	"fmt"
	"net/http"
	"net/mail"
	"net/url"
	"strings"
	"time"

	"github.com/flingra/flingra/backend/internal/email"
)

type Service struct {
	repo              repository
	mailer            email.Sender
	appBaseURL        string
	sessionTTL        time.Duration
	sessionCookieName string
}

func NewService(db *sql.DB, mailer email.Sender, appBaseURL string, sessionTTL time.Duration, secureCookies bool) *Service {
	cookieName := "flingra_session"
	if secureCookies {
		cookieName = "__Host-flingra_session"
	}
	return &Service{
		repo:              repository{db: db},
		mailer:            mailer,
		appBaseURL:        appBaseURL,
		sessionTTL:        sessionTTL,
		sessionCookieName: cookieName,
	}
}

var dummyPasswordHash = "$argon2id$v=19$m=65536,t=3,p=1$c29tZXNhbHRmb3Jub3JtYWxpemVk$ZHVtbXlvdXRwdXRub3R1c2Vk"

type APIError struct {
	Status    int
	Code      string
	Message   string
	Field     string
	RequestID string
}

func (e *APIError) Error() string { return e.Message }

func (s *Service) Register(ctx context.Context, req RegisterRequest) error {
	emailAddress, err := normalizeEmail(req.Email)
	if err != nil {
		return validationError("email", "Enter a valid email address.")
	}
	if len(req.Password) < 12 || len(req.Password) > 128 {
		return validationError("password", "Use a password between 12 and 128 characters.")
	}
	dob, err := time.Parse("2006-01-02", req.DateOfBirth)
	if err != nil || ageAt(dob, time.Now()) < 21 {
		return validationError("date_of_birth", "You must be at least 21 years old.")
	}
	req.Gender = strings.ToLower(strings.TrimSpace(req.Gender))
	if req.Gender != "male" && req.Gender != "female" {
		return validationError("gender", "Select male or female.")
	}
	req.Emergency.Name = strings.TrimSpace(req.Emergency.Name)
	if req.Emergency.Name == "" || len(req.Emergency.Name) > 100 {
		return validationError("emergency_contact.name", "Enter a name of 1 to 100 characters.")
	}
	req.Emergency.PhoneE164 = strings.TrimSpace(req.Emergency.PhoneE164)
	if !validE164(req.Emergency.PhoneE164) {
		return validationError("emergency_contact.phone_e164", "Enter a valid E.164 phone number.")
	}
	if strings.TrimSpace(req.TermsVersion) == "" || strings.TrimSpace(req.PrivacyVersion) == "" {
		return validationError("terms_version", "Terms and privacy policy versions are required.")
	}
	passwordHash, err := hashPassword(req.Password)
	if err != nil {
		return fmt.Errorf("hash password: %w", err)
	}
	token, err := randomToken(32)
	if err != nil {
		return fmt.Errorf("create verification token: %w", err)
	}
	id, err := randomID("mem_")
	if err != nil {
		return fmt.Errorf("create member identifier: %w", err)
	}
	created, err := s.repo.createPendingAccount(ctx, id, emailAddress, passwordHash, dob.Format("2006-01-02"),
		req.Gender, req.Emergency.Name, req.Emergency.PhoneE164,
		strings.TrimSpace(req.TermsVersion), strings.TrimSpace(req.PrivacyVersion),
		hashToken(token), time.Now().Add(30*time.Minute))
	if err != nil {
		return err
	}
	if !created {
		return nil
	}
	verifyURL, err := verificationURL(s.appBaseURL, token)
	if err != nil {
		return err
	}
	if err := s.mailer.SendVerification(ctx, emailAddress, verifyURL); err != nil {
		return fmt.Errorf("verification email delivery failed: %w", err)
	}
	return nil
}

func (s *Service) VerifyEmail(ctx context.Context, token string) (string, error) {
	if token == "" || len(token) > 256 {
		return "", &APIError{Status: http.StatusUnprocessableEntity, Code: "INVALID_TOKEN", Message: "The verification link is invalid or expired."}
	}
	memberID, err := s.repo.verifyEmail(ctx, string(hashToken(token)))
	if errors.Is(err, errNotFound) {
		return "", &APIError{Status: http.StatusUnprocessableEntity, Code: "INVALID_TOKEN", Message: "The verification link is invalid or expired."}
	}
	return memberID, err
}

func (s *Service) Login(ctx context.Context, req LoginRequest) (account, string, string, time.Time, error) {
	emailAddress, err := normalizeEmail(req.Identifier)
	if err != nil {
		_, _ = verifyPassword(dummyPasswordHash, req.Password)
		return account{}, "", "", time.Time{}, invalidCredentials()
	}
	member, err := s.repo.accountByEmail(ctx, emailAddress)
	if errors.Is(err, errNotFound) {
		_, _ = verifyPassword(dummyPasswordHash, req.Password)
		return account{}, "", "", time.Time{}, invalidCredentials()
	}
	if err != nil {
		return account{}, "", "", time.Time{}, err
	}
	valid, err := verifyPassword(member.PasswordHash, req.Password)
	if err != nil {
		return account{}, "", "", time.Time{}, fmt.Errorf("verify stored password: %w", err)
	}
	if !valid {
		return account{}, "", "", time.Time{}, invalidCredentials()
	}
	if !member.EmailVerified {
		return account{}, "", "", time.Time{}, &APIError{Status: http.StatusForbidden, Code: "EMAIL_NOT_VERIFIED", Message: "Verify your email address before signing in."}
	}
	token, err := randomToken(32)
	if err != nil {
		return account{}, "", "", time.Time{}, fmt.Errorf("create session token: %w", err)
	}
	sessionID, err := randomID("ses_")
	if err != nil {
		return account{}, "", "", time.Time{}, fmt.Errorf("create session identifier: %w", err)
	}
	expiresAt := time.Now().Add(s.sessionTTL)
	if err := s.repo.createSession(ctx, sessionID, member.ID, hashToken(token), expiresAt); err != nil {
		return account{}, "", "", time.Time{}, err
	}
	return member, token, csrfForSession(token), expiresAt, nil
}

func (s *Service) CurrentSession(ctx context.Context, token string) (MemberSession, error) {
	session, accountState, verified, err := s.repo.sessionByHash(ctx, hashToken(token))
	if errors.Is(err, errNotFound) {
		return MemberSession{}, &APIError{Status: http.StatusUnauthorized, Code: "UNAUTHENTICATED", Message: "Sign in to continue."}
	}
	if err != nil {
		return MemberSession{}, err
	}
	return MemberSession{
		MemberID:        session.MemberID,
		AccountState:    accountState,
		ContactVerified: verified,
		CSRFToken:       csrfForSession(token),
	}, nil
}

func (s *Service) Logout(ctx context.Context, token string) error {
	session, _, _, err := s.repo.sessionByHash(ctx, hashToken(token))
	if errors.Is(err, errNotFound) {
		return nil
	}
	if err != nil {
		return err
	}
	return s.repo.revokeSession(ctx, session.ID)
}

func (s *Service) Cookie(token string, expiresAt time.Time) *http.Cookie {
	return &http.Cookie{
		Name:     s.sessionCookieName,
		Value:    token,
		Path:     "/",
		HttpOnly: true,
		Secure:   s.sessionCookieName == "__Host-flingra_session",
		SameSite: http.SameSiteLaxMode,
		Expires:  expiresAt,
		MaxAge:   int(time.Until(expiresAt).Seconds()),
	}
}

func (s *Service) ClearCookie() *http.Cookie {
	cookie := s.Cookie("", time.Unix(1, 0))
	cookie.MaxAge = -1
	return cookie
}

func (s *Service) CookieName() string { return s.sessionCookieName }

func (s *Service) ValidCSRF(cookieToken, csrfToken string) bool {
	if cookieToken == "" || csrfToken == "" {
		return false
	}
	expected := csrfForSession(cookieToken)
	return hmac.Equal([]byte(expected), []byte(csrfToken))
}

func csrfForSession(sessionToken string) string {
	mac := hmac.New(sha256.New, []byte(sessionToken))
	_, _ = mac.Write([]byte("flingra-csrf-v1"))
	return base64.RawURLEncoding.EncodeToString(mac.Sum(nil))
}

func normalizeEmail(value string) (string, error) {
	value = strings.ToLower(strings.TrimSpace(value))
	parsed, err := mail.ParseAddress(value)
	if err != nil || parsed.Address != value || len(value) > 254 {
		return "", errors.New("invalid email address")
	}
	return value, nil
}

func ageAt(dob, now time.Time) int {
	age := now.Year() - dob.Year()
	if now.Month() < dob.Month() || (now.Month() == dob.Month() && now.Day() < dob.Day()) {
		age--
	}
	return age
}

func validE164(value string) bool {
	if len(value) < 8 || len(value) > 16 || value[0] != '+' {
		return false
	}
	for _, character := range value[1:] {
		if character < '0' || character > '9' {
			return false
		}
	}
	return true
}

func randomToken(size int) (string, error) {
	buffer := make([]byte, size)
	if _, err := rand.Read(buffer); err != nil {
		return "", err
	}
	return base64.RawURLEncoding.EncodeToString(buffer), nil
}

func randomID(prefix string) (string, error) {
	token, err := randomToken(16)
	if err != nil {
		return "", err
	}
	return prefix + token, nil
}

func verificationURL(baseURL, token string) (string, error) {
	parsed, err := url.Parse(baseURL)
	if err != nil {
		return "", fmt.Errorf("parse application URL: %w", err)
	}
	parsed.Path = strings.TrimRight(parsed.Path, "/") + "/verify-email"
	query := parsed.Query()
	query.Set("token", token)
	parsed.RawQuery = query.Encode()
	return parsed.String(), nil
}

func invalidCredentials() *APIError {
	return &APIError{Status: http.StatusUnauthorized, Code: "INVALID_CREDENTIALS", Message: "Email or password is incorrect."}
}

func validationError(field, message string) *APIError {
	return &APIError{
		Status:  http.StatusUnprocessableEntity,
		Code:    "VALIDATION_FAILED",
		Message: message,
		Field:   field,
	}
}
