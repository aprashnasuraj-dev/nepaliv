using NepaliV.Studio.Domain;

namespace NepaliV.Studio.Generation;

/// <summary>Deterministic OFFLINE composition sketches, not a learned lyricist or audio singer.</summary>
public sealed class OfflineSketchGenerator
{
    private static readonly string[] Roles = ["Intro", "Verse 1", "Pre-Chorus", "Chorus", "Verse 2", "Bridge", "Final Chorus", "Outro"];

    public SongDocument Generate(CreativeBrief brief, int take)
    {
        if (string.IsNullOrWhiteSpace(brief.Intent)) throw new ArgumentException("Describe a feeling or story.");
        if (brief.Modernity is < 0 or > 100) throw new ArgumentOutOfRangeException(nameof(brief.Modernity));
        var rng = new Random(HashCodeStable(brief.Intent, brief.Seed, take));
        int bpm = Math.Clamp(68 + brief.Modernity / 4 + rng.Next(-6, 7), 55, 145);
        string[] progression = take % 3 switch
        {
            0 => ["Am", "F", "C", "G"],
            1 => ["Dm", "G", "C", "Am"],
            _ => ["C", "G", "Am", "F"]
        };
        var sections = Roles.Select((role, index) =>
        {
            string[] lines = role is "Intro" or "Outro"
                ? [brief.Language == SongLanguage.Nepali ? "वाद्य प्रस्तावना — भावना खुल्दै" : "वाद्य प्रस्तावना — एहसास उभरता है"]
                : MakeLines(brief, role, take);
            int[] motif = index is 3 or 6 ? [0, 4, 7, 5, 4, 2, 0, 2] : [0, 2, 4, 2, 5, 4, 2, 0];
            int pitchBase = 60 + (take % 3) * 2;
            NoteEvent[] notes = Enumerable.Range(0, 16)
                .Select(i => new NoteEvent(Math.Clamp(pitchBase + motif[i % motif.Length] + (index == 5 ? 2 : 0), 48, 84), i * 480, 420))
                .ToArray();
            return new SongSection(Guid.NewGuid(), role, lines, (string[])progression.Clone(), notes);
        }).ToArray();
        return new SongDocument(Guid.NewGuid(), 1, $"Take {take + 1} · {brief.Tradition}", brief, bpm, 480, sections, "offline-symbolic-sketch", DateTimeOffset.UtcNow);
    }

    private static string[] MakeLines(CreativeBrief brief, string role, int take)
    {
        string theme = brief.Intent.Trim().Replace('\r', ' ').Replace('\n', ' ');
        if (theme.Length > 72) theme = theme[..72] + "…";
        // Scaffolding deliberately exposes the *user* theme; it must never be marketed as authored poetic lyrics.
        return brief.Language == SongLanguage.Nepali
            ? [$"【{role}】 {theme}", "यहाँ कथाको पहिलो चित्र लेख्नुहोस्", "लयसँग मिल्ने शब्द र विराम परिमार्जन गर्नुहोस्", $"भावनाको मोड — संस्करण {take + 1}"]
            : [$"【{role}】 {theme}", "यहाँ कहानी की पहली तस्वीर लिखें", "लय के अनुसार शब्द और विराम सँवारें", $"भावना का मोड़ — रूप {take + 1}"];
    }

    private static int HashCodeStable(string s, int seed, int take)
    {
        unchecked { uint h = 2166136261; foreach (char c in s) h = (h ^ c) * 16777619; return (int)((h ^ (uint)seed ^ (uint)take * 2654435761u) & 0x7fffffff); }
    }
}
