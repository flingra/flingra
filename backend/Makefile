.PHONY: test vet fmt migrate-up run

test:
	go test ./...

vet:
	go vet ./...

fmt:
	gofmt -w $$(find . -name '*.go' -not -path './vendor/*')

migrate-up:
	docker compose run --rm migrate up

run:
	docker compose up --build api
