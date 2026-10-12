using System.IO;
using System.Text;
using NepaliV.Studio.Domain;
namespace NepaliV.Studio.Export;

/// <summary>Standard MIDI File format 1, conductor tempo track plus separate section tracks.</summary>
public static class MidiExporter
{
    public static void Write(SongDocument song, string destination)
    {
        ArgumentNullException.ThrowIfNull(song);
        if (song.TicksPerBeat is < 24 or > 32767) throw new ArgumentOutOfRangeException(nameof(song));
        using var output = new FileStream(destination, FileMode.Create, FileAccess.Write, FileShare.None);
        output.Write("MThd"u8);
        Be32(output, 6); Be16(output, 1); Be16(output, checked((ushort)(song.Sections.Length + 1))); Be16(output, (ushort)song.TicksPerBeat);
        using (var tempo = new MemoryStream())
        {
            int micros = 60_000_000 / Math.Clamp(song.BeatsPerMinute, 30, 300);
            tempo.Write([0, 0xff, 0x51, 0x03, (byte)(micros >> 16), (byte)(micros >> 8), (byte)micros, 0, 0xff, 0x2f, 0]);
            Track(output, tempo.ToArray());
        }
        int sectionOffset = 0;
        foreach (SongSection section in song.Sections)
        {
            using var tr = new MemoryStream();
            var name = Encoding.UTF8.GetBytes(section.Role);
            tr.WriteByte(0); tr.WriteByte(0xff); tr.WriteByte(0x03); Var(tr, name.Length); tr.Write(name);
            var events = section.Melody.SelectMany(n => new[] { (tick: checked(sectionOffset + n.StartTick), on: true, pitch: n.Pitch), (tick: checked(sectionOffset + n.StartTick + n.DurationTicks), on: false, pitch: n.Pitch) })
                .OrderBy(x => x.tick).ThenBy(x => x.on).ToArray();
            int previous = 0;
            foreach (var e in events)
            {
                if (e.tick < previous || e.pitch is < 0 or > 127) throw new InvalidDataException("Invalid note data");
                Var(tr, e.tick - previous); tr.WriteByte(e.on ? (byte)0x90 : (byte)0x80);
                tr.WriteByte((byte)e.pitch); tr.WriteByte(e.on ? (byte)92 : (byte)0);
                previous = e.tick;
            }
            tr.Write([0, 0xff, 0x2f, 0]); Track(output, tr.ToArray());
            int notesEnd = section.Melody.Length == 0 ? 0 : section.Melody.Max(n => checked(n.StartTick + n.DurationTicks));
            sectionOffset = checked(sectionOffset + Math.Max(notesEnd, section.Chords.Length * song.TicksPerBeat * 4));
        }
    }
    private static void Track(Stream s, byte[] bytes) { s.Write("MTrk"u8); Be32(s, bytes.Length); s.Write(bytes); }
    private static void Be16(Stream s, int v) { s.WriteByte((byte)(v >> 8)); s.WriteByte((byte)v); }
    private static void Be32(Stream s, int v) { s.WriteByte((byte)(v >> 24)); s.WriteByte((byte)(v >> 16)); s.WriteByte((byte)(v >> 8)); s.WriteByte((byte)v); }
    private static void Var(Stream s, int v) { if (v < 0) throw new ArgumentOutOfRangeException(nameof(v)); uint x = (uint)v; Span<byte> bytes = stackalloc byte[5]; int n = 0; bytes[n++] = (byte)(x & 0x7f); while ((x >>= 7) != 0) bytes[n++] = (byte)((x & 0x7f) | 0x80); while (n > 0) s.WriteByte(bytes[--n]); }
}
