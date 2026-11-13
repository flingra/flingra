package main

import (
	"context"
	"database/sql"
	"errors"
	"fmt"
	"log"
	"os"
	"time"

	"github.com/flingra/flingra/backend/internal/migrate"
	_ "github.com/go-sql-driver/mysql"
)

func main() {
	if len(os.Args) != 2 || os.Args[1] != "up" {
		log.Fatal("usage: migrate up")
	}
	dsn := os.Getenv("DATABASE_DSN")
	if dsn == "" {
		log.Fatal("DATABASE_DSN is required")
	}
	db, err := sql.Open("mysql", dsn)
	if err != nil {
		log.Fatal("could not configure database connection")
	}
	defer db.Close()
	db.SetConnMaxLifetime(5 * time.Minute)
	db.SetMaxOpenConns(4)
	db.SetMaxIdleConns(2)
	ctx, cancel := context.WithTimeout(context.Background(), 45*time.Second)
	defer cancel()
	if err := db.PingContext(ctx); err != nil {
		log.Fatal("database is unavailable")
	}
	if err := migrate.Up(ctx, db); err != nil {
		if errors.Is(err, context.DeadlineExceeded) {
			log.Fatal("migration timed out")
		}
		log.Fatal(fmt.Errorf("migration failed: %w", err))
	}
	log.Print("database migrations are up to date")
}
