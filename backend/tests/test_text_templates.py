from types import SimpleNamespace

from app.services.text_templates import apply_template_by_id, resolve_text_templates


def test_disabled_template_effects_keep_parameters_but_apply_as_zero() -> None:
    block = SimpleNamespace(
        font_family="Tahoma",
        font_size=20,
        color_hex="#000000",
        bold=False,
        italic=False,
        text_align="center",
        text_direction="horizontal",
        extra_metadata={},
    )
    settings = {
        "text_templates": {
            "custom": {
                "font_stack": ["Tahoma"],
                "font_size": 32,
                "stroke_enabled": False,
                "stroke_width": 6,
                "outline_glow_enabled": False,
                "outline_glow_radius": 14,
                "outline_glow_opacity": 0.7,
            }
        }
    }

    assert apply_template_by_id(block, "custom", settings) is True
    assert settings["text_templates"]["custom"]["stroke_width"] == 6
    assert settings["text_templates"]["custom"]["outline_glow_radius"] == 14
    assert block.extra_metadata["stroke_width"] == 0
    assert block.extra_metadata["outline_glow_radius"] == 0
    assert block.extra_metadata["outline_glow_opacity"] == 0


def test_builtin_auto_templates_share_the_six_point_minimum() -> None:
    templates = resolve_text_templates(None)

    assert templates
    assert all(template["auto_font_size"] is True for template in templates.values())
    assert all(template["min_font_size"] == 6 for template in templates.values())
