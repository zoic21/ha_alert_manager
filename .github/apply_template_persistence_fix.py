from pathlib import Path

panel_path = Path("frontend-src/alert-manager-panel.js")
panel = panel_path.read_text()

old = '''    element.addEventListener("value-changed", (event) => {
      const eventValue = event.detail && Object.hasOwn(event.detail, "value")
        ? event.detail.value
        : element.value;
      if (eventValue !== undefined) onChange(eventValue);
    });'''
new = '''    element.addEventListener("value-changed", (event) => {
      const eventValue = event.detail && Object.hasOwn(event.detail, "value")
        ? event.detail.value
        : element.value;
      if (eventValue !== undefined) {
        // Home Assistant selectors are controlled components: their host
        // value is not updated automatically when the inner selector emits
        // value-changed. Mirror the value so later reads are never stale.
        element.value = eventValue;
        onChange(eventValue);
      }
    });'''
if old not in panel:
    raise SystemExit("Expected _configureSelector listener not found")
panel = panel.replace(old, new, 1)

old = '''      message: String(
        this.shadowRoot.querySelector("#rule-message-template")?.value
          ?? this._editingRule?.message
          ?? "",
      ).trim() || null,
      condition_template: String(
        this.shadowRoot.querySelector("#rule-condition-template")?.value
          ?? this._editingRule?.condition_template
          ?? "",
      ).trim() || null,'''
new = '''      message: String(
        this._editingRule?.message
          ?? this.shadowRoot.querySelector("#rule-message-template")?.value
          ?? "",
      ).trim() || null,
      condition_template: String(
        this._editingRule?.condition_template
          ?? this.shadowRoot.querySelector("#rule-condition-template")?.value
          ?? "",
      ).trim() || null,'''
if old not in panel:
    raise SystemExit("Expected rule save template block not found")
panel = panel.replace(old, new, 1)

old = '''      message: String(
        this.shadowRoot.querySelector("#rule-message-template")?.value
          ?? this._editingRule.message
          ?? "",
      ),
      condition_template: String(
        this.shadowRoot.querySelector("#rule-condition-template")?.value
          ?? this._editingRule.condition_template
          ?? "",
      ),'''
new = '''      message: String(
        this._editingRule.message
          ?? this.shadowRoot.querySelector("#rule-message-template")?.value
          ?? "",
      ),
      condition_template: String(
        this._editingRule.condition_template
          ?? this.shadowRoot.querySelector("#rule-condition-template")?.value
          ?? "",
      ),'''
if old not in panel:
    raise SystemExit("Expected rule draft template block not found")
panel = panel.replace(old, new, 1)
panel_path.write_text(panel)

tests_path = Path("tests/frontend.test.mjs")
tests = tests_path.read_text()
test_name = "controlled selectors mirror emitted values back to their host"
if test_name not in tests:
    tests += r'''

test("controlled selectors mirror emitted values back to their host", () => {
  const Panel = customElements.get("alert-manager-panel");
  const panel = new Panel();
  panel._hass = {};
  const selector = {
    value: "",
    addEventListener(type, listener) {
      if (type === "value-changed") this.listener = listener;
    },
  };
  panel.shadowRoot.querySelector = (query) => query === "#template-test" ? selector : null;
  let changed;

  panel._configureSelector(
    "template-test",
    { template: {} },
    "",
    (value) => { changed = value; },
  );
  selector.listener({ detail: { value: "{{ true }}" } });

  assert.equal(selector.value, "{{ true }}");
  assert.equal(changed, "{{ true }}");
});

test("new rule saves message and condition drafts when selector hosts still expose empty initial values", async () => {
  const Panel = customElements.get("alert-manager-panel");
  const panel = new Panel();
  panel._config = completeConfig();
  panel._editingRule = {
    ...newRuleDefaults(),
    ...ruleValues(),
    message: "Alerte {{ states('sensor.example') }}",
    condition_template: "{{ is_state('binary_sensor.example', 'on') }}",
  };
  const ruleForm = form(ruleValues());
  panel.shadowRoot.querySelector = (selector) => {
    if (selector === "#rule-message-template") return { value: "" };
    if (selector === "#rule-condition-template") return { value: "" };
    return null;
  };
  panel._render = () => {};
  const calls = [];
  panel._hass = {
    callWS: async (message) => {
      calls.push(message);
      return { ...message.rule, id: "created-rule", version: 2 };
    },
  };

  await panel._saveRule(ruleForm);

  assert.equal(calls.length, 1);
  assert.equal(calls[0].rule.message, "Alerte {{ states('sensor.example') }}");
  assert.equal(
    calls[0].rule.condition_template,
    "{{ is_state('binary_sensor.example', 'on') }}",
  );
});
'''
    tests_path.write_text(tests)

changelog_path = Path("CHANGELOG.md")
changelog = changelog_path.read_text()
marker = "# Changelog\n\nToutes les évolutions notables d’Alert Manager sont documentées dans ce fichier.\n\n"
section = """## 1.7.2 — 27 août 2026

### Corrigé

- Correction de la sauvegarde des champs **Message** et **Condition Jinja supplémentaire** des règles personnalisées. Les `ha-selector` de Home Assistant sont des composants contrôlés : leur propriété `value` ne se met pas à jour automatiquement lorsque l’éditeur Jinja interne émet `value-changed`. Alert Manager réinjecte maintenant explicitement la nouvelle valeur dans le sélecteur et utilise le brouillon de règle comme source de vérité lors de la sauvegarde.
- La suppression volontaire du contenu de ces champs reste correctement enregistrée comme valeur vide (`null` côté stockage).

### Tests

- Ajout d’un test reproduisant le comportement réel du sélecteur Template Home Assistant avec une propriété hôte restée vide après saisie.
- Ajout d’un test vérifiant la synchronisation de la valeur des sélecteurs contrôlés.

"""
if "## 1.7.2 — 27 août 2026" not in changelog:
    if marker not in changelog:
        raise SystemExit("Changelog header not found")
    changelog_path.write_text(changelog.replace(marker, marker + section, 1))

manifest_path = Path("custom_components/alert_manager/manifest.json")
manifest = manifest_path.read_text()
if '"version": "1.7.1"' not in manifest:
    raise SystemExit("manifest version 1.7.1 not found")
manifest_path.write_text(manifest.replace('"version": "1.7.1"', '"version": "1.7.2"', 1))

const_path = Path("custom_components/alert_manager/const.py")
const = const_path.read_text()
if 'INTEGRATION_VERSION: Final = "1.7.1"' not in const:
    raise SystemExit("const version 1.7.1 not found")
const_path.write_text(const.replace('INTEGRATION_VERSION: Final = "1.7.1"', 'INTEGRATION_VERSION: Final = "1.7.2"', 1))

package_path = Path("package.json")
package = package_path.read_text()
if '"version": "1.7.1"' not in package:
    raise SystemExit("package version 1.7.1 not found")
package_path.write_text(package.replace('"version": "1.7.1"', '"version": "1.7.2"', 1))
