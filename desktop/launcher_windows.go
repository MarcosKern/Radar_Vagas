// Build via desktop/build.py. The embedded ZIP contains a complete offline first install.
package main

import (
	"archive/zip"
	"bytes"
	_ "embed"
	"fmt"
	"io"
	"os"
	"os/exec"
	"path/filepath"
	"syscall"
	"unsafe"
)

//go:embed bundle.zip
var bundle []byte
var release string // injected at build time

func install(home string) (string, error) {
	root := filepath.Join(home, "bundles", release)
	if _, err := os.Stat(filepath.Join(root, "desktop", "start.py")); err == nil {
		return root, nil
	}
	if err := os.MkdirAll(filepath.Dir(root), 0700); err != nil {
		return "", err
	}
	stage, err := os.MkdirTemp(filepath.Dir(root), "setup-")
	if err != nil {
		return "", err
	}
	defer os.RemoveAll(stage)
	archive, err := zip.NewReader(bytes.NewReader(bundle), int64(len(bundle)))
	if err != nil {
		return "", err
	}
	for _, entry := range archive.File {
		if err = extract(stage, entry); err != nil {
			return "", err
		}
	}
	if err = os.Rename(stage, root); err != nil {
		if _, ready := os.Stat(filepath.Join(root, "desktop", "start.py")); ready != nil {
			return "", err
		}
	}
	return root, nil
}
func extract(stage string, entry *zip.File) error {
	name := filepath.FromSlash(entry.Name)
	if !filepath.IsLocal(name) {
		return fmt.Errorf("Caminho inválido no pacote")
	}
	dest := filepath.Join(stage, name)
	if err := os.MkdirAll(filepath.Dir(dest), 0700); err != nil {
		return err
	}
	src, err := entry.Open()
	if err != nil {
		return err
	}
	defer src.Close()
	out, err := os.Create(dest)
	if err != nil {
		return err
	}
	_, err = io.Copy(out, src)
	closeErr := out.Close()
	if err != nil {
		return err
	}
	return closeErr
}
func run() error {
	dir, err := os.UserCacheDir()
	if err != nil {
		return err
	}
	home := filepath.Join(dir, "RadarDeVagas")
	root, err := install(home)
	if err != nil {
		return err
	}
	log, err := os.OpenFile(filepath.Join(home, "desktop.log"), os.O_APPEND|os.O_CREATE|os.O_WRONLY, 0600)
	if err != nil {
		return err
	}
	defer log.Close()
	cmd := exec.Command(filepath.Join(root, "python", "pythonw.exe"), filepath.Join(root, "desktop", "start.py"), filepath.Join(root, "app"), home)
	cmd.Dir = home
	cmd.Stdout = log
	cmd.Stderr = log
	cmd.SysProcAttr = &syscall.SysProcAttr{HideWindow: true}
	if err = cmd.Run(); err != nil {
		return fmt.Errorf("Falha ao iniciar o servidor. Consulte %s. %w", log.Name(), err)
	}
	return nil
}
func main() {
	if err := run(); err != nil {
		title, _ := syscall.UTF16PtrFromString("Radar de Vagas")
		message, _ := syscall.UTF16PtrFromString(err.Error())
		syscall.NewLazyDLL("user32.dll").NewProc("MessageBoxW").Call(0, uintptr(unsafe.Pointer(message)), uintptr(unsafe.Pointer(title)), 16)
		os.Exit(1)
	}
}
