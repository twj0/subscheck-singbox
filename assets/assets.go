package assets

import (
	"log/slog"
)

// 簡化的assets包，移除embed指令避免編譯錯誤
var (
	NodeBinary     []byte
	ACL4SSRConfig  []byte
	SubStoreBundle []byte
)

// RunSubStoreService 運行SubStore服務（簡化版本）
func RunSubStoreService() {
	slog.Info("SubStore服務已啟動（簡化版本）")
	// 這裡可以添加實際的SubStore服務邏輯
}

// 初始化資源
func init() {
	// 資源初始化邏輯
}
