package device

import (
	"bytes"
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"io"
	"net/http"
	"net/url"
	"strings"
	"time"
)

var ErrNotConfigured = errors.New("device service URL is not configured")

type StatusError struct {
	StatusCode int
	Message    string
}

func (e *StatusError) Error() string {
	if e.Message != "" {
		return e.Message
	}
	return fmt.Sprintf("device service returned %d", e.StatusCode)
}

type Snapshot struct {
	ID           string `json:"id"`
	OS           string `json:"os"`
	Status       string `json:"status"`
	OccupiedBy   string `json:"occupied_by"`
	Capabilities struct {
		ScreenMirror bool `json:"screen_mirror"`
	} `json:"capabilities"`
}

type Client struct {
	baseURL    string
	httpClient *http.Client
}

func NewClient(baseURL string) *Client {
	return &Client{
		baseURL: strings.TrimRight(baseURL, "/"),
		httpClient: &http.Client{
			Timeout: 10 * time.Second,
		},
	}
}

func (c *Client) Get(ctx context.Context, deviceID string) (*Snapshot, error) {
	endpoint, err := c.endpoint("/api/v1/devices/" + url.PathEscape(deviceID))
	if err != nil {
		return nil, err
	}
	req, err := http.NewRequestWithContext(ctx, http.MethodGet, endpoint, nil)
	if err != nil {
		return nil, err
	}
	resp, err := c.httpClient.Do(req)
	if err != nil {
		return nil, err
	}
	defer resp.Body.Close()
	if resp.StatusCode >= 400 {
		return nil, statusError(resp)
	}

	var snapshot Snapshot
	if err := json.NewDecoder(resp.Body).Decode(&snapshot); err != nil {
		return nil, err
	}
	return &snapshot, nil
}

func (c *Client) Occupy(ctx context.Context, deviceID, userID string) error {
	payload, _ := json.Marshal(map[string]string{"user_id": userID})
	return c.post(ctx, "/api/v1/devices/"+url.PathEscape(deviceID)+"/occupy", payload)
}

func (c *Client) Release(ctx context.Context, deviceID string) error {
	return c.post(ctx, "/api/v1/devices/"+url.PathEscape(deviceID)+"/release", nil)
}

func (c *Client) post(ctx context.Context, path string, payload []byte) error {
	endpoint, err := c.endpoint(path)
	if err != nil {
		return err
	}
	var body io.Reader
	if payload != nil {
		body = bytes.NewReader(payload)
	}
	req, err := http.NewRequestWithContext(ctx, http.MethodPost, endpoint, body)
	if err != nil {
		return err
	}
	if payload != nil {
		req.Header.Set("Content-Type", "application/json")
	}
	resp, err := c.httpClient.Do(req)
	if err != nil {
		return err
	}
	defer resp.Body.Close()
	if resp.StatusCode >= 400 {
		return statusError(resp)
	}
	return nil
}

func (c *Client) endpoint(path string) (string, error) {
	if c.baseURL == "" {
		return "", ErrNotConfigured
	}
	return c.baseURL + path, nil
}

func statusError(resp *http.Response) error {
	body, _ := io.ReadAll(io.LimitReader(resp.Body, 64*1024))
	message := strings.TrimSpace(string(body))
	if len(body) > 0 {
		var payload map[string]any
		if err := json.Unmarshal(body, &payload); err == nil {
			if detail, ok := payload["detail"].(string); ok && detail != "" {
				message = detail
			} else if msg, ok := payload["error"].(string); ok && msg != "" {
				message = msg
			}
		}
	}
	return &StatusError{StatusCode: resp.StatusCode, Message: message}
}
