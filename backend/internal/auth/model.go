package auth

import "time"

type RegisterRequest struct {
	Email       string `json:"email"`
	Password    string `json:"password"`
	DateOfBirth string `json:"date_of_birth"`
	Gender      string `json:"gender"`
	Emergency   struct {
		Name      string `json:"name"`
		PhoneE164 string `json:"phone_e164"`
	} `json:"emergency_contact"`
	TermsVersion   string `json:"terms_version"`
	PrivacyVersion string `json:"privacy_version"`
}

type LoginRequest struct {
	Identifier string `json:"identifier"`
	Password   string `json:"password"`
}

type VerifyEmailRequest struct {
	Token string `json:"token"`
}

type MemberSession struct {
	MemberID        string `json:"member_id"`
	AccountState    string `json:"account_state"`
	ContactVerified bool   `json:"contact_verified"`
	CSRFToken       string `json:"csrf_token"`
}

type account struct {
	ID            string
	Email         string
	PasswordHash  string
	EmailVerified bool
	CreatedAt     time.Time
}

type sessionRecord struct {
	ID        string
	MemberID  string
	ExpiresAt time.Time
}
