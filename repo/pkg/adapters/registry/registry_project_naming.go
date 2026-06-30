package registry

import (
	"fmt"
	"strings"
	"unicode"

	"github.com/kubercloud/ani/pkg/ports"
)

const (
	registryDefaultProjectName = "default"
	registryMaxProjectNameLen  = 128
)

func validateRegistryProjectName(name string) error {
	name = strings.TrimSpace(name)
	if name == "" {
		return fmt.Errorf("%w: project is required", ports.ErrInvalid)
	}
	if len(name) > registryMaxProjectNameLen {
		return fmt.Errorf("%w: project name must be at most %d characters", ports.ErrInvalid, registryMaxProjectNameLen)
	}
	if strings.Contains(name, "..") {
		return fmt.Errorf("%w: project name must not contain '..'", ports.ErrInvalid)
	}
	first := rune(name[0])
	if !unicode.IsLetter(first) && !unicode.IsDigit(first) {
		return fmt.Errorf("%w: project name must start with a letter or digit", ports.ErrInvalid)
	}
	for _, r := range name {
		if unicode.IsLetter(r) || unicode.IsDigit(r) || r == '.' || r == '-' || r == '_' {
			continue
		}
		return fmt.Errorf("%w: project name contains invalid character %q", ports.ErrInvalid, string(r))
	}
	if strings.HasPrefix(name, ".") || strings.HasSuffix(name, ".") || strings.HasPrefix(name, "-") || strings.HasSuffix(name, "-") {
		return fmt.Errorf("%w: project name must not start or end with '.' or '-'", ports.ErrInvalid)
	}
	return nil
}

func validateRegistryProjectRequest(tenantID, project string) error {
	if strings.TrimSpace(tenantID) == "" {
		return fmt.Errorf("%w: tenant_id is required", ports.ErrInvalid)
	}
	return validateRegistryProjectName(project)
}

func tenantProjectStorageKey(tenantID, name string) string {
	return strings.TrimSpace(tenantID) + "\x00" + strings.TrimSpace(name)
}

func harborProjectPrefix(tenantID string) string {
	compact := strings.ReplaceAll(strings.TrimSpace(tenantID), "-", "")
	return "ani-" + compact + "-"
}

// harborProviderProjectName maps an ANI tenant project name to a Harbor project name.
// Legacy: when aniName equals tenantID, Harbor project name remains tenantID (Sprint13 live gate).
func harborProviderProjectName(tenantID, aniName string) string {
	tenantID = strings.TrimSpace(tenantID)
	aniName = strings.TrimSpace(aniName)
	if aniName == tenantID {
		return tenantID
	}
	return harborProjectPrefix(tenantID) + sanitizeRegistryNameSegment(aniName)
}

func aniProjectNameFromHarbor(tenantID, harborName string) (string, bool) {
	tenantID = strings.TrimSpace(tenantID)
	harborName = strings.TrimSpace(harborName)
	if harborName == tenantID {
		return tenantID, true
	}
	prefix := harborProjectPrefix(tenantID)
	if !strings.HasPrefix(harborName, prefix) {
		return "", false
	}
	aniName := strings.TrimPrefix(harborName, prefix)
	if aniName == "" {
		return "", false
	}
	return aniName, true
}

func resolveHarborProjectName(tenantID, aniProject string) (string, error) {
	if err := validateRegistryProjectRequest(tenantID, aniProject); err != nil {
		return "", err
	}
	return harborProviderProjectName(tenantID, aniProject), nil
}

func resolveImageProjectNames(tenantID, imageProject string) (harborProject, aniProject string, err error) {
	imageProject = strings.TrimSpace(imageProject)
	tenantID = strings.TrimSpace(tenantID)
	if imageProject == "" {
		return "", "", fmt.Errorf("%w: image project is required", ports.ErrInvalid)
	}
	if aniName, ok := aniProjectNameFromHarbor(tenantID, imageProject); ok {
		return imageProject, aniName, nil
	}
	if err := validateRegistryProjectName(imageProject); err != nil {
		return "", "", err
	}
	return harborProviderProjectName(tenantID, imageProject), imageProject, nil
}

func sanitizeRegistryNameSegment(name string) string {
	cleaned := strings.Map(func(r rune) rune {
		switch {
		case r >= 'a' && r <= 'z', r >= '0' && r <= '9', r == '.', r == '-', r == '_':
			return r
		case r >= 'A' && r <= 'Z':
			return r + ('a' - 'A')
		default:
			return '-'
		}
	}, strings.TrimSpace(name))
	cleaned = strings.Trim(cleaned, ".-")
	if cleaned == "" {
		return "project"
	}
	return cleaned
}

func localRegistryProjectID(tenantID, name string) string {
	return "regproj-" + sanitizeRegistryNameSegment(tenantID) + "-" + sanitizeRegistryNameSegment(name)
}
