package config

import (
	"time"

	"github.com/spf13/viper"
)

type Config struct {
	Server   ServerConfig
	Scrcpy   ScrcpyConfig
	WebRTC   WebRTCConfig
	Device   DeviceConfig
	LogLevel string
}

type ServerConfig struct {
	Host string
	Port int
}

type ScrcpyConfig struct {
	MaxResolution int
	MaxFPS        int
	BitRate       int
	Codec        string
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
	viper.SetDefault("webrtc.min_port", 40000)
	viper.SetDefault("webrtc.max_port", 50000)
	// Default ICE servers (can be overridden via config file or env)
	viper.SetDefault("webrtc.ice_servers", []map[string]interface{}{
		{
			"urls": []string{"stun:stun.l.google.com:19302", "stun:stun1.l.google.com:19302"},
		},
	})
	viper.SetDefault("device.service_url", "http://device-svc:8001")
	viper.SetDefault("log_level", "info")

	// Environment variable overrides
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
			Codec:        viper.GetString("scrcpy.codec"),
		},
		WebRTC: WebRTCConfig{
			ICEServers: iceServers,
			MinPort:    viper.GetInt("webrtc.min_port"),
			MaxPort:    viper.GetInt("webrtc.max_port"),
		},
		Device: DeviceConfig{
			ServiceURL: viper.GetString("device.service_url"),
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
