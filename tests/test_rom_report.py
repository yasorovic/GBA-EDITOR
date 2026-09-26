from codegen.rom_report import RomReport, format_report


def test_rom_report_is_a_textual_category_summary_without_ascii_gauges():
    report = RomReport(
        rom_bytes=45_600,
        cartridge_bytes=4 * 1024 * 1024,
        categories={"Graphismes": 18_240, "Audio": 27_360},
    )

    lines = format_report(report)

    assert "  Graphismes — 17.8 KiB (40.0 %)" in lines
    assert "  Audio — 26.7 KiB (60.0 %)" in lines
    assert any(line.startswith("  Total — 44.5 KiB / 4 MiB") for line in lines)
    assert not any("█" in line or "·" in line for line in lines)
