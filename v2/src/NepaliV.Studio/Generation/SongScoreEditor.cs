using NepaliV.Studio.Domain;
namespace NepaliV.Studio.Generation;
public static class SongScoreEditor
{
    public static SongDocument Apply(SongDocument song, string score)
    {
        if (score.Length > 100000) throw new ArgumentException("Editor too large.");
        var result = new List<SongSection>();
        SongSection? current = null;
        List<string> lines = [];
        int index = 0;
        void Finish()
        {
            if (current is null) return;
            if (lines.Count == 0 || lines.Any(l => l.Length > 500)) throw new ArgumentException("Empty or oversized section.");
            result.Add(current with { Lines = lines.ToArray() });
            lines = [];
        }
        foreach (string raw in score.Replace("\r", "").Split('\n'))
        {
            var line = raw.Trim();
            if (line.StartsWith("── ") && line.EndsWith(" ──"))
            {
                Finish();
                if (index >= song.Sections.Length) throw new ArgumentException("Too many sections.");
                current = song.Sections[index++];
                if (line[3..^3].Trim() != current.Role) throw new ArgumentException("Section headers cannot be rearranged.");
            }
            else if (current is not null && line.Length > 0 && line != string.Join("  ·  ", current.Chords)) lines.Add(line);
        }
        Finish();
        if (index != song.Sections.Length) throw new ArgumentException("All section headings must be retained.");
        return song with { Sections = result.ToArray(), Revision = checked(song.Revision + 1) };
    }
}