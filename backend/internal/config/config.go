package config

import (
	"errors"
	"fmt"
	"net/url"
	"os"
	"strconv"
	"strings"
	"time"
)

type Config struct {
	Environment         string
	HTTPAddr            string
	DatabaseDSN         string
	BrevoAPIKey         string
	EmailFromAddress    string
	EmailFromName       string
	AppBaseURL          string
	AllowedOrigins      []string
	SessionCookieSecure bool
	SessionTTL          time.Duration
	ReadTimeout         time.Duration
	ReadHeaderTimeout   time.Duration
	WriteTimeout        time.Duration
	IdleTimeout         time.Duration
	DatabasePingTimeout time.Duration
	MaxRequestBodyBytes int64
}

func Load() (Config, error) {
	cfg := Config{
		Environment:         strings.TrimSpace(os.Getenv("APP_ENV")),
		HTTPAddr:            strings.TrimSpace(os.Getenv("HTTP_ADDR")),
		DatabaseDSN:         strings.TrimSpace(os.Getenv("DATABASE_DSN")),
		BrevoAPIKey:         strings.TrimSpace(os.Getenv("BREVO_API_KEY")),
		EmailFromAddress:    strings.TrimSpace(os.Getenv("EMAIL_FROM_ADDRESS")),
		EmailFromName:       strings.TrimSpace(os.Getenv("EMAIL_FROM_NAME")),
		AppBaseURL:          strings.TrimSpace(os.Getenv("APP_BASE_URL")),
		AllowedOrigins:      splitCSV(os.Getenv("ALLOWED_ORIGINS")),
		ReadTimeout:         10 * time.Second,
		ReadHeaderTimeout:   5 * time.Second,
		WriteTimeout:        15 * time.Second,
		IdleTimeout:         60 * time.Second,
		DatabasePingTimeout: 3 * time.Second,
		MaxRequestBodyBytes: 1 << 20,
	}

	if cfg.Environment == "" {
		cfg.Environment = "development"
	}
	if cfg.HTTPAddr == "" {
		cfg.HTTPAddr = ":8080"
	}
	if cfg.EmailFromName == "" {
		cfg.EmailFromName = "Flingra"
	}

	var err error
	if cfg.SessionCookieSecure, err = parseBoolEnv("SESSION_COOKIE_SECURE", cfg.Environment == "production"); err != nil {
		return Config{}, err
	}
	cfg.SessionTTL, err = parseDurationEnv("SESSION_TTL", 12*time.Hour)
	if err != nil {
		return Config{}, err
	}

	if cfg.DatabaseDSN == "" {
		return Config{}, errors.New("DATABASE_DSN is required")
	}
	if cfg.BrevoAPIKey == "" {
		return Config{}, errors.New("BREVO_API_KEY is required")
	}
	if cfg.EmailFromAddress == "" || !strings.Contains(cfg.EmailFromAddress, "@") {
		return Config{}, errors.New("EMAIL_FROM_ADDRESS must be a valid email address")
	}
	if !validHTTPURL(cfg.AppBaseURL) {
		return Config{}, errors.New("APP_BASE_URL must be an absolute HTTP(S) URL")
	}
	if len(cfg.AllowedOrigins) == 0 {
		return Config{}, errors.New("ALLOWED_ORIGINS must contain at least one exact origin")
	}
	if cfg.Environment == "production" && !cfg.SessionCookieSecure {
		return Config{}, errors.New("SESSION_COOKIE_SECURE must be true in production")
	}
	if cfg.SessionTTL < time.Minute || cfg.SessionTTL > 24*time.Hour {
		return Config{}, errors.New("SESSION_TTL must be between 1m and 24h")
	}
	for _, origin := range cfg.AllowedOrigins {
		if !validOrigin(origin) {
			return Config{}, errors.New("ALLOWED_ORIGINS contains an invalid origin")
		}
	}
	return cfg, nil
}

func splitCSV(value string) []string {
	values := strings.Split(value, ",")
	result := make([]string, 0, len(values))
	for _, value := range values {
		if value = strings.TrimSpace(value); value != "" {
			result = append(result, value)
		}
	}
	return result
}

func parseBoolEnv(key string, fallback bool) (bool, error) {
	value := strings.TrimSpace(os.Getenv(key))
	if value == "" {
		return fallback, nil
	}
	parsed, err := strconv.ParseBool(value)
	if err != nil {
		return false, fmt.Errorf("%s must be true or false", key)
	}
	return parsed, nil
}

func parseDurationEnv(key string, fallback time.Duration) (time.Duration, error) {
	value := strings.TrimSpace(os.Getenv(key))
	if value == "" {
		return fallback, nil
	}
	parsed, err := time.ParseDuration(value)
	if err != nil {
		return 0, fmt.Errorf("%s must be a valid duration", key)
	}
	return parsed, nil
}

func validHTTPURL(value string) bool {
	parsed, err := url.ParseRequestURI(value)
	return err == nil && (parsed.Scheme == "http" || parsed.Scheme == "https") && parsed.Host != ""
}

func validOrigin(value string) bool {
	parsed, err := url.ParseRequestURI(value)
	return err == nil &&
		(parsed.Scheme == "http" || parsed.Scheme == "https") &&
		parsed.Host != "" &&
		parsed.Path == "" &&
		parsed.RawQuery == "" &&
		parsed.Fragment == "" &&
		parsed.User == nil
}
