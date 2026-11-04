from whisper_gui.grammar_panel import GrammarPanel


def test_clicking_analyze_emits_analyze_requested(qapp):
    panel = GrammarPanel()
    received = []
    panel.analyze_requested.connect(lambda: received.append(True))
    panel.analyze_button.click()
    assert received == [True]


def test_set_result_shows_the_analysis_text(qapp):
    panel = GrammarPanel()
    panel.set_result("# Heading\nSome analysis text.")
    assert "Some analysis text." in panel.result_view.toPlainText()


def test_set_status_updates_the_status_label(qapp):
    panel = GrammarPanel()
    panel.set_status("Analyzing...")
    assert panel.status_label.text() == "Analyzing..."


def test_set_analyze_enabled_toggles_the_button(qapp):
    panel = GrammarPanel()
    panel.set_analyze_enabled(False)
    assert panel.analyze_button.isEnabled() is False
    panel.set_analyze_enabled(True)
    assert panel.analyze_button.isEnabled() is True


def test_clear_resets_result_and_status(qapp):
    panel = GrammarPanel()
    panel.set_result("text")
    panel.set_status("Analyzing...")
    panel.clear()
    assert panel.result_view.toPlainText() == ""
    assert panel.status_label.text() == ""
