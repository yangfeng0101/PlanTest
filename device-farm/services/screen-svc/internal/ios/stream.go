package ios

import (
	"context"
	"encoding/json"
	"fmt"
	"io"
	"net/http"
	"net/url"
	"strings"
	"time"
)

type StreamSession struct {
	DeviceID      string   `json:"device_id"`
	SessionID     string   `json:"session_id"`
	MJPEGURL      string   `json:"mjpeg_url"`
	MJPEGPort     int      `json:"mjpeg_port"`
	SessionReused bool     `json:"session_reused"`
	Screen        *Screen  `json:"screen"`
	Settings      Settings `json:"settings"`
}

type Screen struct {
	Width  int `json:"width"`
	Height int `json:"height"`
}

type Settings struct {
	MJPEGServerFramerate int `json:"mjpegServerFramerate"`
}

type SourceResponse struct {
	DeviceID      string `json:"device_id"`
	Source        string `json:"source"`
	SessionReused bool   `json:"session_reused"`
}

func StartAgentStreamSession(ctx context.Context, agentURL string, deviceID string) (*StreamSession, error) {
	agentURL = strings.TrimRight(agentURL, "/")
	if agentURL == "" {
		return nil, fmt.Errorf("IOS_AGENT_URL is not configured for iOS screen streaming")
	}

	endpoint := agentURL + "/devices/" + url.PathEscape(deviceID) + "/stream-session"
	req, err := http.NewRequestWithContext(ctx, http.MethodPost, endpoint, nil)
	if err != nil {
		return nil, err
	}
	resp, err := http.DefaultClient.Do(req)
	if err != nil {
		return nil, fmt.Errorf("failed to call iOS Agent stream session: %w", err)
	}
	defer resp.Body.Close()

	body, _ := io.ReadAll(io.LimitReader(resp.Body, 1024*1024))
	if resp.StatusCode >= 400 {
		return nil, fmt.Errorf("iOS Agent stream session failed with HTTP %d: %s", resp.StatusCode, string(body))
	}

	var stream StreamSession
	if err := json.Unmarshal(body, &stream); err != nil {
		return nil, fmt.Errorf("invalid iOS Agent stream session response: %w", err)
	}
	if stream.MJPEGURL == "" {
		return nil, fmt.Errorf("iOS Agent did not return an MJPEG URL")
	}
	return &stream, nil
}

func GetAgentSource(ctx context.Context, agentURL string, deviceID string) (*SourceResponse, error) {
	agentURL = strings.TrimRight(agentURL, "/")
	if agentURL == "" {
		return nil, fmt.Errorf("IOS_AGENT_URL is not configured for iOS page source")
	}

	endpoint := agentURL + "/devices/" + url.PathEscape(deviceID) + "/source"
	req, err := http.NewRequestWithContext(ctx, http.MethodGet, endpoint, nil)
	if err != nil {
		return nil, err
	}
	resp, err := http.DefaultClient.Do(req)
	if err != nil {
		return nil, fmt.Errorf("failed to call iOS Agent page source: %w", err)
	}
	defer resp.Body.Close()

	body, _ := io.ReadAll(io.LimitReader(resp.Body, 1024*1024))
	if resp.StatusCode >= 400 {
		return nil, fmt.Errorf("iOS Agent page source failed with HTTP %d: %s", resp.StatusCode, string(body))
	}

	var source SourceResponse
	if err := json.Unmarshal(body, &source); err != nil {
		return nil, fmt.Errorf("invalid iOS Agent page source response: %w", err)
	}
	if source.Source == "" {
		return nil, fmt.Errorf("iOS Agent returned an empty page source")
	}
	return &source, nil
}

func StopAgentStreamSession(ctx context.Context, agentURL string, deviceID string) error {
	agentURL = strings.TrimRight(agentURL, "/")
	if agentURL == "" {
		return nil
	}

	reqCtx, cancel := context.WithTimeout(ctx, 10*time.Second)
	defer cancel()
	endpoint := agentURL + "/devices/" + url.PathEscape(deviceID) + "/stream-session"
	req, err := http.NewRequestWithContext(reqCtx, http.MethodDelete, endpoint, nil)
	if err != nil {
		return err
	}
	resp, err := http.DefaultClient.Do(req)
	if err != nil {
		return err
	}
	defer resp.Body.Close()
	if resp.StatusCode >= 400 {
		body, _ := io.ReadAll(io.LimitReader(resp.Body, 64*1024))
		return fmt.Errorf("iOS Agent stream session release failed with HTTP %d: %s", resp.StatusCode, string(body))
	}
	return nil
}
