from pathlib import Path


panel_path = Path("frontend-src/alert-manager-panel.js")
panel = panel_path.read_text()
old = '''      condition_template: String(
        this.shadowRoot.querySelector("#rule-condition-template")?.value ?? "",
      ).trim() || null,'''
new = '''      condition_template: String(
        this.shadowRoot.querySelector("#rule-condition-template")?.value
          ?? this._editingRule?.condition_template
          ?? "",
      ).trim() || null,'''
if old not in panel:
    raise SystemExit("Expected condition_template save block not found")
panel_path.write_text(panel.replace(old, new, 1))


tests_path = Path("tests/frontend.test.mjs")
tests = tests_path.read_text()
test_name = (
    "new rule preserves Jinja condition from selector draft when selector value is unavailable"
)
if test_name not in tests:
    tests += r'''

test("new rule preserves Jinja condition from selector draft when selector value is unavailable", async () => {
  const Panel = customElements.get("alert-manager-panel");
  const panel = new Panel();
  panel._config = completeConfig();
  panel._editingRule = {
    ...newRuleDefaults(),
    ...ruleValues(),
    condition_template: "{{ states('sensor.example') == 'on' }}",
  };
  const ruleForm = form(ruleValues());
  panel.shadowRoot.querySelector = (selector) => {
    if (selector === "#rule-condition-template") return { value: undefined };
    if (selector === "#rule-message-template") return { value: "" };
    return null;
  };
  panel._render = () => {};
  const calls = [];
  panel._hass = {
    callWS: async (message) => {
      calls.push(message);
      return { ...message.rule, id: "created-rule" };
    },
  };

  await panel._saveRule(ruleForm);

  assert.equal(calls.length, 1);
  assert.equal(calls[0].type, "alert_manager/rules/create");
  assert.equal(
    calls[0].rule.condition_template,
    "{{ states('sensor.example') == 'on' }}",
  );
});
'''
    tests_path.write_text(tests)


changelog_path = Path("CHANGELOG.md")
changelog = changelog_path.read_text()
marker = (
    "# Changelog\n\n"
    "Toutes les évolutions notables d’Alert Manager sont documentées dans ce fichier.\n\n"
)
section = """## 1.7.1 — 27 août 2026

### Corrigé

- Lors de la création d’une règle personnalisée, la condition Jinja supplémentaire
  est désormais récupérée depuis le brouillon de l’éditeur lorsque le composant
  `ha-selector` de Home Assistant n’expose pas encore sa nouvelle valeur via sa
  propriété `.value` au moment de la sauvegarde. Le texte saisi n’est donc plus
  remplacé par une valeur vide à la création de la règle.

### Tests

- Un test frontend reproduit le cas où le sélecteur Jinja a déjà mis à jour le
  brouillon mais expose encore une propriété `.value` indisponible au moment de
  la sauvegarde.

"""
if "## 1.7.1 — 27 août 2026" not in changelog:
    if marker not in changelog:
        raise SystemExit("Changelog header not found")
    changelog_path.write_text(changelog.replace(marker, marker + section, 1))
