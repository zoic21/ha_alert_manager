export function navigate(path, newTabInBrowser = false) {
    if (!path) return;
    const inCompanionApp = Boolean(
      globalThis.window?.externalApp
      || globalThis.window?.externalAppV2
      || globalThis.window?.webkit?.messageHandlers?.externalBus
    );
    if (newTabInBrowser && !inCompanionApp && typeof window.open === "function") {
      window.open(path, "_blank", "noopener,noreferrer");
      return;
    }
    window.history?.pushState?.(null, "", path);
    window.dispatchEvent?.(new CustomEvent("location-changed", {
      detail: { replace: false },
    }));
}
