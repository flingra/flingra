package auth

import (
	"encoding/json"
	"errors"
	"io"
	"log/slog"
	"net/http"
	"strings"

	"github.com/flingra/flingra/backend/internal/requestmeta"
)

type HTTPHandler struct {
	service *Service
	logger  *slog.Logger
}

func NewHTTPHandler(service *Service, logger *slog.Logger) *HTTPHandler {
	return &HTTPHandler{service: service, logger: logger}
}

func (h *HTTPHandler) RegisterRoutes(mux *http.ServeMux) {
	mux.HandleFunc("POST /api/v1/auth/register", h.register)
	mux.HandleFunc("POST /api/v1/auth/email-verification/confirm", h.verifyEmail)
	mux.HandleFunc("POST /api/v1/auth/login", h.login)
	mux.HandleFunc("GET /api/v1/auth/session", h.session)
	mux.HandleFunc("POST /api/v1/auth/logout", h.logout)
}

func (h *HTTPHandler) register(w http.ResponseWriter, r *http.Request) {
	var request RegisterRequest
	if !decodeJSON(w, r, &request) {
		writeError(w, &APIError{Status: http.StatusBadRequest, Code: "INVALID_REQUEST", Message: "Request body must be valid JSON."})
		return
	}
	if err := h.service.Register(r.Context(), request); err != nil {
		h.writeServiceError(w, r, "registration", err)
		return
	}
	writeJSON(w, http.StatusAccepted, map[string]string{"status": "accepted", "next_step": "verify_email"})
}

func (h *HTTPHandler) verifyEmail(w http.ResponseWriter, r *http.Request) {
	var request VerifyEmailRequest
	if !decodeJSON(w, r, &request) {
		writeError(w, &APIError{Status: http.StatusBadRequest, Code: "INVALID_REQUEST", Message: "Request body must be valid JSON."})
		return
	}
	memberID, err := h.service.VerifyEmail(r.Context(), request.Token)
	if err != nil {
		h.writeServiceError(w, r, "email verification", err)
		return
	}
	writeJSON(w, http.StatusOK, map[string]string{"member_id": memberID, "account_state": "age_review_required"})
}

func (h *HTTPHandler) login(w http.ResponseWriter, r *http.Request) {
	var request LoginRequest
	if !decodeJSON(w, r, &request) {
		writeError(w, &APIError{Status: http.StatusBadRequest, Code: "INVALID_REQUEST", Message: "Request body must be valid JSON."})
		return
	}
	member, token, csrf, expiresAt, err := h.service.Login(r.Context(), request)
	if err != nil {
		h.writeServiceError(w, r, "login", err)
		return
	}
	http.SetCookie(w, h.service.Cookie(token, expiresAt))
	writeJSON(w, http.StatusOK, MemberSession{
		MemberID:        member.ID,
		AccountState:    "age_review_required",
		ContactVerified: member.EmailVerified,
		CSRFToken:       csrf,
	})
}

func (h *HTTPHandler) session(w http.ResponseWriter, r *http.Request) {
	token, ok := h.sessionToken(w, r)
	if !ok {
		return
	}
	session, err := h.service.CurrentSession(r.Context(), token)
	if err != nil {
		h.writeServiceError(w, r, "session lookup", err)
		return
	}
	writeJSON(w, http.StatusOK, session)
}

func (h *HTTPHandler) logout(w http.ResponseWriter, r *http.Request) {
	token, ok := h.sessionToken(w, r)
	if !ok {
		return
	}
	if !h.service.ValidCSRF(token, r.Header.Get("X-CSRF-Token")) {
		writeError(w, &APIError{Status: http.StatusForbidden, Code: "CSRF_FAILED", Message: "Refresh your session and try again."})
		return
	}
	if err := h.service.Logout(r.Context(), token); err != nil {
		h.writeServiceError(w, r, "logout", err)
		return
	}
	http.SetCookie(w, h.service.ClearCookie())
	w.WriteHeader(http.StatusNoContent)
}

func (h *HTTPHandler) sessionToken(w http.ResponseWriter, r *http.Request) (string, bool) {
	cookie, err := r.Cookie(h.service.CookieName())
	if err != nil || strings.TrimSpace(cookie.Value) == "" {
		writeError(w, &APIError{Status: http.StatusUnauthorized, Code: "UNAUTHENTICATED", Message: "Sign in to continue."})
		return "", false
	}
	return cookie.Value, true
}

func (h *HTTPHandler) writeServiceError(w http.ResponseWriter, r *http.Request, operation string, err error) {
	var apiErr *APIError
	if errors.As(err, &apiErr) {
		writeError(w, apiErr)
		return
	}
	requestID := requestmeta.ID(r.Context())
	apiErr.RequestID = requestID
	h.logger.Error("backend operation failed", "operation", operation, "request_id", requestID, "error", err)
	if operation == "registration" {
		writeError(w, &APIError{Status: http.StatusServiceUnavailable, Code: "EMAIL_DELIVERY_UNAVAILABLE", Message: "We could not send the verification email. Please try again shortly."})
		return
	}
	writeError(w, &APIError{Status: http.StatusInternalServerError, Code: "INTERNAL_ERROR", Message: "The request could not be completed."})
}

func decodeJSON(w http.ResponseWriter, r *http.Request, destination any) bool {
	if !strings.HasPrefix(r.Header.Get("Content-Type"), "application/json") {
		return false
	}
	decoder := json.NewDecoder(r.Body)
	decoder.DisallowUnknownFields()
	if err := decoder.Decode(destination); err != nil {
		return false
	}
	var trailing any
	return errors.Is(decoder.Decode(&trailing), io.EOF)
}

func writeJSON(w http.ResponseWriter, status int, value any) {
	w.Header().Set("Content-Type", "application/json; charset=utf-8")
	w.WriteHeader(status)
	_ = json.NewEncoder(w).Encode(value)
}

func writeError(w http.ResponseWriter, apiErr *APIError) {
	type fieldError struct {
		Field   string `json:"field"`
		Code    string `json:"code"`
		Message string `json:"message"`
	}
	type errorDetails struct {
		Code        string       `json:"code"`
		Message     string       `json:"message"`
		RequestID   string       `json:"request_id,omitempty"`
		FieldErrors []fieldError `json:"field_errors,omitempty"`
	}
	type response struct {
		Error errorDetails `json:"error"`
	}
	details := errorDetails{Code: apiErr.Code, Message: apiErr.Message, RequestID: apiErr.RequestID}
	if apiErr.Field != "" {
		details.FieldErrors = []fieldError{{Field: apiErr.Field, Code: apiErr.Code, Message: apiErr.Message}}
	}
	writeJSON(w, apiErr.Status, response{Error: details})
}
