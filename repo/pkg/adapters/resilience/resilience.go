package resilience

import (
	"context"
	"errors"
	"time"
)

type Policy struct {
	Timeout        time.Duration
	MaxAttempts    int
	BaseBackoff    time.Duration
	MaxBackoff     time.Duration
	BreakerName    string
	FailureRatio   float64
	MinRequests    uint32
	CooldownPeriod time.Duration
}

var ErrCircuitOpen = errors.New("circuit open")

func Retryable(err error) bool {
	return false
}

func Do(ctx context.Context, policy Policy, fn func(context.Context) error) error {
	if policy.Timeout <= 0 {
		return fn(ctx)
	}
	callCtx, cancel := context.WithTimeout(ctx, policy.Timeout)
	defer cancel()
	return fn(callCtx)
}
