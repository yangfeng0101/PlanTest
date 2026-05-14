package config

import (
	"strings"
	"time"

	"github.com/spf13/viper"
)

type Config struct {
	Server   ServerConfig
	Scrcpy   ScrcpyConfig
	IOSAgent IOSAgentConfig
	WebRTC   WebRTCConfig
	LiveKit  LiveKitConfig
	Device   DeviceConfig
	Auth     AuthConfig
	LogLevel string
}

type ServerConfig struct {
	Host string
	Port int
}

type LiveKitConfig struct {
	URL       string
	PublicURL string
	APIKey    string
	APISecret string
}

type ScrcpyConfig struct {
	MaxResolution int
	MaxFPS        int
	BitRate       int
	Codec         string
	ServerPath    string
}

type IOSAgentConfig struct {
	URL string
}

type WebRTCConfig struct {
	ICEServers []ICEServer
	MinPort    int
	MaxPort    int
}

type ICEServer struct {
	URLs       []string
	Username   string
	Credential string
}

type DeviceConfig struct {
	ServiceURL string
}

type AuthConfig struct {
	Enabled        bool
	TestServiceURL string
}

func Load() *Config {
	viper.SetConfigName("config")
	viper.SetConfigType("yaml")
	viper.AddConfigPath(".")
	viper.AddConfigPath("./config")

	// Set defaults
	viper.SetDefault("server.host", "0.0.0.0")
	viper.SetDefault("server.port", 8002)
	viper.SetDefault("scrcpy.max_resolution", 1080)
	viper.SetDefault("scrcpy.max_fps", 30)
	viper.SetDefault("scrcpy.bit_rate", 2000000)
	viper.SetDefault("scrcpy.codec", "h264")
	viper.SetDefault("scrcpy.server_path", "/usr/share/scrcpy/scrcpy-server")
	viper.SetDefault("ios_agent.url", "")
	viper.SetDefault("webrtc.min_port", 40000)
	viper.SetDefault("webrtc.max_port", 50000)
	// Default ICE servers (can be overridden via config file or env)
	viper.SetDefault("webrtc.ice_servers", []map[string]interface{}{
		{
			"urls": []string{"stun:stun.l.google.com:19302", "stun:stun1.l.google.com:19302"},
		},
	})
	viper.SetDefault("device.service_url", "http://device-svc:8001")
	viper.SetDefault("auth.enabled", true)
	viper.SetDefault("auth.test_service_url", "http://test-svc:8001")
	viper.SetDefault("log_level", "info")

	viper.SetDefault("livekit.url", "ws://livekit:7880")
	viper.SetDefault("livekit.public_url", "ws://localhost:7880")
	viper.SetDefault("livekit.api_key", "devkey")
	viper.SetDefault("livekit.api_secret", "secret")

	// Environment variable overrides
	viper.SetEnvKeyReplacer(strings.NewReplacer(".", "_"))
	viper.BindEnv("auth.test_service_url", "TEST_SVC_URL", "AUTH_TEST_SERVICE_URL")
	viper.BindEnv("device.service_url", "DEVICE_SVC_URL", "DEVICE_SERVICE_URL")
	viper.AutomaticEnv()

	if err := viper.ReadInConfig(); err != nil {
		if _, ok := err.(viper.ConfigFileNotFoundError); !ok {
			panic(err)
		}
	}

	// Parse ICE servers from config
	var iceServers []ICEServer
	if err := viper.UnmarshalKey("webrtc.ice_servers", &iceServers); err != nil || len(iceServers) == 0 {
		// Fallback to default
		iceServers = []ICEServer{
			{
				URLs: []string{"stun:stun.l.google.com:19302", "stun:stun1.l.google.com:19302"},
			},
		}
	}

	return &Config{
		Server: ServerConfig{
			Host: viper.GetString("server.host"),
			Port: viper.GetInt("server.port"),
		},
		Scrcpy: ScrcpyConfig{
			MaxResolution: viper.GetInt("scrcpy.max_resolution"),
			MaxFPS:        viper.GetInt("scrcpy.max_fps"),
			BitRate:       viper.GetInt("scrcpy.bit_rate"),
			Codec:         viper.GetString("scrcpy.codec"),
			ServerPath:    viper.GetString("scrcpy.server_path"),
		},
		IOSAgent: IOSAgentConfig{
			URL: strings.TrimRight(viper.GetString("ios_agent.url"), "/"),
		},
		WebRTC: WebRTCConfig{
			ICEServers: iceServers,
			MinPort:    viper.GetInt("webrtc.min_port"),
			MaxPort:    viper.GetInt("webrtc.max_port"),
		},
		LiveKit: LiveKitConfig{
			URL:       viper.GetString("livekit.url"),
			PublicURL: viper.GetString("livekit.public_url"),
			APIKey:    viper.GetString("livekit.api_key"),
			APISecret: viper.GetString("livekit.api_secret"),
		},
		Device: DeviceConfig{
			ServiceURL: viper.GetString("device.service_url"),
		},
		Auth: AuthConfig{
			Enabled:        viper.GetBool("auth.enabled"),
			TestServiceURL: viper.GetString("auth.test_service_url"),
		},
		LogLevel: viper.GetString("log_level"),
	}
}

func (c *Config) GetAddress() string {
	return viper.GetString("server.host") + ":" + viper.GetString("server.port")
}

func (c *Config) GetReadTimeout() time.Duration {
	return 30 * time.Second
}

func (c *Config) GetWriteTimeout() time.Duration {
	return 30 * time.Second
}
