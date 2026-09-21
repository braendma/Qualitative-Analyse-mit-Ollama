# Lizenznachtrag: Silero-VAD-Hilfsmodell

Das Windows-Standalone-Paket enthält `_internal/faster_whisper/assets/silero_vad_v6.onnx` (1.245.151 Bytes) als Hilfsmodell zur Erkennung von Sprachaktivität. Dieses Hilfsmodell ist getrennt von den zusätzlich zu installierenden Whisper- und Sprechererkennungsmodellen zu betrachten.

## Herkunft und Lizenz

- **Silero VAD v6.0**, offizieller Tag-Commit `fba061dc5559f696e62171e9a0741782b0fdc23c`: MIT License, Copyright (c) 2020-present Silero Team. Der vollständige, unveränderte Text liegt in `Silero-VAD-LICENSE.txt`.
- Offizielle Lizenzquelle: https://github.com/snakers4/silero-vad/blob/fba061dc5559f696e62171e9a0741782b0fdc23c/LICENSE
- **faster-whisper 1.2.1**, offizieller Tag-Commit `65882eee9f5cdbeeb2d877f1131d48cf241b327d`: MIT License, Copyright (c) 2023 SYSTRAN. Der unveränderte Text liegt ergänzend in `faster-whisper-LICENSE.txt` und ist bereits im Paket enthalten.
- Offizielle Integrationsquelle: https://github.com/SYSTRAN/faster-whisper/blob/65882eee9f5cdbeeb2d877f1131d48cf241b327d/faster_whisper/assets/silero_vad_v6.onnx
- Offizieller Herkunftsnachweis: https://github.com/SYSTRAN/faster-whisper/commit/dea24cbcc6cbef23ff599a63be0bbb647a0b23d6 (`Upgrade to Silero-VAD V6`).

Die Datei im ausgelieferten Paket stimmt mit dem Git-Blob des faster-whisper-Release exakt überein. Sie wird nicht als byteidentisch zum anders verpackten ONNX-Modell im Silero-Repository bezeichnet. Prüfsummen und Abrufquellen sind in `PROVENANCE.json` erfasst.

Die MIT-Lizenz verlangt die Beibehaltung des Copyright- und Erlaubnisvermerks in Kopien beziehungsweise wesentlichen Teilen. Diese Lizenzdateien sind deshalb bei Weitergabe des Hilfsmodells mitzuführen. Die vollständigen Lizenztexte enthalten auch den Gewährleistungs- und Haftungsausschluss.

Dieser Nachtrag ändert keinen Programmcode, keine Modelle und keine Produktressourcen. Er wurde separat vorbereitet; die Übernahme in die Lieferung erfolgt gesondert.
