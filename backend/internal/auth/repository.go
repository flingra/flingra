package auth

import (
	"context"
	"crypto/sha256"
	"database/sql"
	"errors"
	"fmt"
	"time"
)

var errNotFound = errors.New("not found")

type repository struct {
	db *sql.DB
}

func (r repository) createPendingAccount(ctx context.Context, id, email, passwordHash, dob, gender, emergencyName, emergencyPhone, termsVersion, privacyVersion string, tokenHash []byte, tokenExpires time.Time) (bool, error) {
	tx, err := r.db.BeginTx(ctx, nil)
	if err != nil {
		return false, fmt.Errorf("begin registration: %w", err)
	}
	defer tx.Rollback()

	var existingID string
	var emailVerified bool
	err = tx.QueryRowContext(ctx, `SELECT id, email_verified FROM accounts WHERE email = ? FOR UPDATE`, email).Scan(&existingID, &emailVerified)
	if err == nil {
		if emailVerified {
			return false, nil
		}
		if _, err = tx.ExecContext(ctx, `DELETE FROM email_verification_tokens WHERE account_id = ?`, existingID); err != nil {
			return false, fmt.Errorf("replace verification challenge: %w", err)
		}
		id = existingID
	} else if !errors.Is(err, sql.ErrNoRows) {
		return false, fmt.Errorf("check existing account: %w", err)
	} else {
		_, err = tx.ExecContext(ctx, `
			INSERT INTO accounts
				(id, email, password_hash, date_of_birth, gender, emergency_contact_name,
				 emergency_contact_phone_e164, terms_version, privacy_version, email_verified, account_state)
			VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, FALSE, 'email_verification_required')`,
			id, email, passwordHash, dob, gender, emergencyName, emergencyPhone, termsVersion, privacyVersion)
		if err != nil {
			return false, fmt.Errorf("create account: %w", err)
		}
	}
	_, err = tx.ExecContext(ctx, `INSERT INTO email_verification_tokens (account_id, token_hash, expires_at) VALUES (?, ?, ?)`,
		id, tokenHash, tokenExpires)
	if err != nil {
		return false, fmt.Errorf("create email verification token: %w", err)
	}
	if err := tx.Commit(); err != nil {
		return false, fmt.Errorf("commit registration: %w", err)
	}
	return true, nil
}

func (r repository) accountByEmail(ctx context.Context, email string) (account, error) {
	var result account
	err := r.db.QueryRowContext(ctx, `
		SELECT id, email, password_hash, email_verified, created_at
		FROM accounts WHERE email = ?`, email).
		Scan(&result.ID, &result.Email, &result.PasswordHash, &result.EmailVerified, &result.CreatedAt)
	if errors.Is(err, sql.ErrNoRows) {
		return account{}, errNotFound
	}
	if err != nil {
		return account{}, fmt.Errorf("load account: %w", err)
	}
	return result, nil
}

func (r repository) verifyEmail(ctx context.Context, tokenHash string) (string, error) {
	tx, err := r.db.BeginTx(ctx, nil)
	if err != nil {
		return "", fmt.Errorf("begin email verification: %w", err)
	}
	defer tx.Rollback()
	var accountID string
	err = tx.QueryRowContext(ctx, `
		SELECT account_id FROM email_verification_tokens
		WHERE token_hash = ? AND expires_at > UTC_TIMESTAMP() FOR UPDATE`, tokenHash).Scan(&accountID)
	if errors.Is(err, sql.ErrNoRows) {
		return "", errNotFound
	}
	if err != nil {
		return "", fmt.Errorf("load email verification token: %w", err)
	}
	if _, err := tx.ExecContext(ctx, `UPDATE accounts SET email_verified = TRUE, account_state = 'age_review_required' WHERE id = ?`, accountID); err != nil {
		return "", fmt.Errorf("verify account email: %w", err)
	}
	if _, err := tx.ExecContext(ctx, `DELETE FROM email_verification_tokens WHERE account_id = ?`, accountID); err != nil {
		return "", fmt.Errorf("consume email verification token: %w", err)
	}
	if err := tx.Commit(); err != nil {
		return "", fmt.Errorf("commit email verification: %w", err)
	}
	return accountID, nil
}

func (r repository) createSession(ctx context.Context, id, memberID string, sessionHash []byte, expiresAt time.Time) error {
	_, err := r.db.ExecContext(ctx, `
		INSERT INTO sessions (id, account_id, session_token_hash, expires_at)
		VALUES (?, ?, ?, ?)`, id, memberID, sessionHash, expiresAt)
	if err != nil {
		return fmt.Errorf("create session: %w", err)
	}
	return nil
}

func (r repository) sessionByHash(ctx context.Context, tokenHash []byte) (sessionRecord, string, bool, error) {
	var session sessionRecord
	var accountState string
	var emailVerified bool
	err := r.db.QueryRowContext(ctx, `
		SELECT s.id, s.account_id, s.expires_at, a.account_state, a.email_verified
		FROM sessions s JOIN accounts a ON a.id = s.account_id
		WHERE s.session_token_hash = ? AND s.expires_at > UTC_TIMESTAMP()
		  AND s.revoked_at IS NULL`, tokenHash).
		Scan(&session.ID, &session.MemberID, &session.ExpiresAt, &accountState, &emailVerified)
	if errors.Is(err, sql.ErrNoRows) {
		return sessionRecord{}, "", false, errNotFound
	}
	if err != nil {
		return sessionRecord{}, "", false, fmt.Errorf("load session: %w", err)
	}
	return session, accountState, emailVerified, nil
}

func (r repository) revokeSession(ctx context.Context, sessionID string) error {
	_, err := r.db.ExecContext(ctx, `UPDATE sessions SET revoked_at = UTC_TIMESTAMP() WHERE id = ? AND revoked_at IS NULL`, sessionID)
	if err != nil {
		return fmt.Errorf("revoke session: %w", err)
	}
	return nil
}

func hashToken(token string) []byte {
	sum := sha256.Sum256([]byte(token))
	return sum[:]
}
