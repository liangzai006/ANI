package resilience

import (
	"context"
	"errors"
	"testing"
	"time"
)

func TestDoEnforcesTimeout(t *testing.T) {
	err := Do(context.Background(), Policy{Timeout: time.Millisecond}, func(ctx context.Context) error {
		<-ctx.Done()
		return ctx.Err()
	})

	if !errors.Is(err, context.DeadlineExceeded) {
		t.Fatalf("Do() error = %v, want context deadline exceeded", err)
	}
}
