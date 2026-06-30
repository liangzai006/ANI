package main

import (
	runtimeadapter "github.com/kubercloud/ani/pkg/adapters/runtime"
	"github.com/kubercloud/ani/pkg/ports"
)

func newGatewayBrandingService(metadata ports.MetadataStore, objectStore ports.ObjectStore) ports.BrandingService {
	var base ports.BrandingService
	if metadata != nil {
		base = runtimeadapter.NewMetadataBrandingService(metadata)
	} else {
		base = runtimeadapter.NewLocalBrandingService()
	}
	if objectStore != nil {
		return runtimeadapter.NewObjectStoreBrandingService(base, objectStore)
	}
	return base
}
