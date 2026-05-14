package device

import (
	"context"
	"encoding/json"
	"errors"
	"net/http"
	"net/http/httptest"
	"testing"
)

func TestClientOccupyAndRelease(t *testing.T) {
	var calls []string
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		calls = append(calls, r.Method+" "+r.URL.Path)
		switch r.URL.Path {
		case "/api/v1/devices/ios-1/occupy":
			if r.Method != http.MethodPost {
				t.Fatalf("unexpected occupy method %s", r.Method)
			}
			var payload map[string]string
			if err := json.NewDecoder(r.Body).Decode(&payload); err != nil {
				t.Fatalf("decode occupy payload: %v", err)
			}
			if payload["user_id"] != "user-1" {
				t.Fatalf("unexpected user_id %q", payload["user_id"])
			}
			w.WriteHeader(http.StatusOK)
		case "/api/v1/devices/ios-1/release":
			if r.Method != http.MethodPost {
				t.Fatalf("unexpected release method %s", r.Method)
			}
			w.WriteHeader(http.StatusOK)
		default:
			t.Fatalf("unexpected path %s", r.URL.Path)
		}
	}))
	defer server.Close()

	client := NewClient(server.URL)
	if err := client.Occupy(context.Background(), "ios-1", "user-1"); err != nil {
		t.Fatalf("occupy failed: %v", err)
	}
	if err := client.Release(context.Background(), "ios-1"); err != nil {
		t.Fatalf("release failed: %v", err)
	}
	if len(calls) != 2 {
		t.Fatalf("expected 2 calls, got %d", len(calls))
	}
}

func TestClientGetAndStatusError(t *testing.T) {
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		switch r.URL.Path {
		case "/api/v1/devices/ios-1":
			_ = json.NewEncoder(w).Encode(map[string]any{
				"id":          "ios-1",
				"os":          "ios",
				"status":      "busy",
				"occupied_by": "user-1",
				"capabilities": map[string]any{
					"screen_mirror": true,
				},
			})
		case "/api/v1/devices/busy/occupy":
			w.WriteHeader(http.StatusBadRequest)
			_ = json.NewEncoder(w).Encode(map[string]string{"detail": "Device is not available"})
		default:
			w.WriteHeader(http.StatusNotFound)
		}
	}))
	defer server.Close()

	client := NewClient(server.URL)
	snapshot, err := client.Get(context.Background(), "ios-1")
	if err != nil {
		t.Fatalf("get failed: %v", err)
	}
	if snapshot.OS != "ios" || snapshot.Status != "busy" || snapshot.OccupiedBy != "user-1" || !snapshot.Capabilities.ScreenMirror {
		t.Fatalf("unexpected snapshot: %+v", snapshot)
	}

	err = client.Occupy(context.Background(), "busy", "user-1")
	var statusErr *StatusError
	if !errors.As(err, &statusErr) {
		t.Fatalf("expected StatusError, got %T: %v", err, err)
	}
	if statusErr.StatusCode != http.StatusBadRequest || statusErr.Message != "Device is not available" {
		t.Fatalf("unexpected status error: %+v", statusErr)
	}
}
