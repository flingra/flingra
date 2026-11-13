package main

import (
	"context"
	"database/sql"
	"errors"
	"log"
	"log/slog"
	"net/http"
	"os"
	"os/signal"
	"syscall"
	"time"

	"github.com/flingra/flingra/backend/internal/auth"
	"github.com/flingra/flingra/backend/internal/config"
	"github.com/flingra/flingra/backend/internal/email"
	"github.com/flingra/flingra/backend/internal/server"
	_ "github.com/go-sql-driver/mysql"
)

func main() {
	cfg, err := config.Load()
	if err != nil {
		log.Fatal("invalid configuration: ", err)
	}
	logger := slog.New(slog.NewJSONHandler(os.Stdout, &slog.HandlerOptions{Level: slog.LevelInfo}))
	db, err := sql.Open("mysql", cfg.DatabaseDSN)
	if err != nil {
		logger.Error("database configuration failed")
		os.Exit(1)
	}
	defer db.Close()
	db.SetMaxOpenConns(20)
	db.SetMaxIdleConns(10)
	db.SetConnMaxLifetime(5 * time.Minute)
	db.SetConnMaxIdleTime(time.Minute)

	pingCtx, cancelPing := context.WithTimeout(context.Background(), cfg.DatabasePingTimeout)
	err = db.PingContext(pingCtx)
	cancelPing()
	if err != nil {
		logger.Error("database is unavailable")
		os.Exit(1)
	}

	mailer := email.NewBrevoClient(cfg.BrevoAPIKey, cfg.EmailFromAddress, cfg.EmailFromName)
	authService := auth.NewService(db, mailer, cfg.AppBaseURL, cfg.SessionTTL, cfg.SessionCookieSecure)
	handler := server.New(server.Dependencies{
		DB:             db,
		Auth:           auth.NewHTTPHandler(authService, logger),
		Logger:         logger,
		AllowedOrigins: cfg.AllowedOrigins,
		MaxBodyBytes:   cfg.MaxRequestBodyBytes,
		PingTimeout:    cfg.DatabasePingTimeout,
	})
	httpServer := &http.Server{
		Addr:              cfg.HTTPAddr,
		Handler:           handler,
		ReadTimeout:       cfg.ReadTimeout,
		ReadHeaderTimeout: cfg.ReadHeaderTimeout,
		WriteTimeout:      cfg.WriteTimeout,
		IdleTimeout:       cfg.IdleTimeout,
		MaxHeaderBytes:    1 << 20,
	}

	shutdownContext, stop := signal.NotifyContext(context.Background(), os.Interrupt, syscall.SIGTERM)
	defer stop()
	go func() {
		<-shutdownContext.Done()
		ctx, cancel := context.WithTimeout(context.Background(), 10*time.Second)
		defer cancel()
		if err := httpServer.Shutdown(ctx); err != nil {
			logger.Error("graceful shutdown failed")
		}
	}()

	logger.Info("api server starting", "address", cfg.HTTPAddr, "environment", cfg.Environment)
	if err := httpServer.ListenAndServe(); err != nil && !errors.Is(err, http.ErrServerClosed) {
		logger.Error("api server stopped unexpectedly")
		os.Exit(1)
	}
}
