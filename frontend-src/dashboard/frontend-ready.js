// Extra frontend modules can run before app.ts installs HA's scoped custom
// element registry polyfill. Wait before evaluating either HTMLElement subclass:
// the polyfill replaces both the global registry and the HTMLElement constructor.
// Native whenDefined also resolves for the shell's polyfill stand-in element.
await customElements.whenDefined("home-assistant");
