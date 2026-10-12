using NepaliV.Studio.Audio;
using NepaliV.Studio.Domain;
using NepaliV.Studio.Export;
using NepaliV.Studio.Generation;
using System.Text.Json;
using System.IO;

var root = Path.Combine(Path.GetTempPath(), "nepaliv-smoke-" + Guid.NewGuid().ToString("N"));
Directory.CreateDirectory(root);
try
{
    var composer = new OfflineSketchGenerator();
    foreach (SongLanguage language in Enum.GetValues<SongLanguage>())
    {
        var prompt = language == SongLanguage.Nepali ? "दसैँमा घरको सम्झना" : "घर से दूर बारिश की रात";
        var brief = new CreativeBrief(prompt, language, "Folk", 40, 1234);
        var takes = Enumerable.Range(0, 3).Select(i => composer.Generate(brief, i)).ToArray();
        if (takes.Select(t => t.Sections[3].Melody[0].Pitch).Distinct().Count() != 3) throw new Exception("Take variation missing.");
        var song = takes[0];
        if (song.Sections.Any(s => s.Lines.Any(l => l.Contains("यहाँ") || l.Contains("【"))))
            throw new Exception("Unfilled lyric scaffold.");
        string serializedView = string.Join("\n", song.Sections.Select(s => "── " + s.Role + " ──\n" +
            string.Join("  ·  ", s.Chords) + "\n" + string.Join("\n", s.Lines)));
        var revised = SongScoreEditor.Apply(song, serializedView);
        if (revised.Revision != song.Revision + 1 ||
            revised.Sections.Any(s => s.Lines.Length == 0)) throw new Exception("Section edit failed.");
        string json = JsonSerializer.Serialize(song);
        if (JsonSerializer.Deserialize<SongDocument>(json)?.Sections.Length != 8) throw new Exception("JSON roundtrip failed.");
        string midi = Path.Combine(root, language + ".mid");
        MidiExporter.Write(song, midi);
        byte[] head = File.ReadAllBytes(midi);
        if (head.Length < 50 || System.Text.Encoding.ASCII.GetString(head, 0, 4) != "MThd") throw new Exception("MIDI invalid.");
        string wave = Path.Combine(root, language + ".wav");
        OfflineAudioRenderer.Render(song, wave);
        byte[] wh = File.ReadAllBytes(wave);
        if (wh.Length < 44100 * 4 || System.Text.Encoding.ASCII.GetString(wh, 0, 4) != "RIFF") throw new Exception("WAV invalid.");
        Console.WriteLine(language + ": 8 sections, three variations, JSON/MIDI/WAV OK (" + wh.Length + " bytes)");
    }
}
finally { Directory.Delete(root, recursive:true); }
