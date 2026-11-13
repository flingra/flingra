package email

import (
	"bytes"
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"html"
	"net/http"
	"net/url"
	"strings"
	"time"
)

const brevoEndpoint = "https://api.brevo.com/v3/smtp/email"

type Sender interface {
	SendVerification(ctx context.Context, to, verifyURL string) error
}

type BrevoClient struct {
	apiKey      string
	fromAddress string
	fromName    string
	client      *http.Client
}

func NewBrevoClient(apiKey, fromAddress, fromName string) *BrevoClient {
	return &BrevoClient{
		apiKey:      apiKey,
		fromAddress: fromAddress,
		fromName:    fromName,
		client:      &http.Client{Timeout: 8 * time.Second},
	}
}

func (c *BrevoClient) SendVerification(ctx context.Context, to, verifyURL string) error {
	if c.apiKey == "" || c.fromAddress == "" {
		return errors.New("email delivery is not configured")
	}
	payload := struct {
		Sender      contact   `json:"sender"`
		To          []contact `json:"to"`
		Subject     string    `json:"subject"`
		TextContent string    `json:"textContent"`
		HTMLContent string    `json:"htmlContent"`
	}{
		Sender:      contact{Name: c.fromName, Email: c.fromAddress},
		To:          []contact{{Email: to}},
		Subject:     "Verify your Flingra email",
		TextContent: "Verify your Flingra email address by opening this link: " + verifyURL + "\nIf you did not create an account, you can ignore this email.",
		HTMLContent: "<p>Verify your Flingra email address:</p><p><a href=\"" + html.EscapeString(verifyURL) + "\">Verify email</a></p><p>If you did not create an account, you can ignore this email.</p>",
	}
	body, err := json.Marshal(payload)
	if err != nil {
		return fmt.Errorf("encode email request: %w", err)
	}
	req, err := http.NewRequestWithContext(ctx, http.MethodPost, brevoEndpoint, bytes.NewReader(body))
	if err != nil {
		return fmt.Errorf("create email request: %w", err)
	}
	req.Header.Set("accept", "application/json")
	req.Header.Set("content-type", "application/json")
	req.Header.Set("api-key", c.apiKey)

	response, err := c.client.Do(req)
	if err != nil {
		return fmt.Errorf("send verification email: %w", err)
	}
	defer response.Body.Close()
	if response.StatusCode < 200 || response.StatusCode >= 300 {
		return fmt.Errorf("email provider returned HTTP %d", response.StatusCode)
	}
	return nil
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

type contact struct {
	Name  string `json:"name,omitempty"`
	Email string `json:"email"`
}
