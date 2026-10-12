using System.IO;
using System.Text;
using NepaliV.Studio.Domain;

namespace NepaliV.Studio.Audio;

/// <summary>Entirely offline, bounded-memory stereo PCM renderer for instrumental composition guides.</summary>
public static class OfflineAudioRenderer
{
    public const int SampleRate = 44100;
    public static void Render(SongDocument song, string path, CancellationToken cancellation = default)
    {
        if (song.BeatsPerMinute is < 30 or > 300 || song.TicksPerBeat is < 24 or > 32767)
            throw new InvalidDataException("Invalid tempo / timing.");
        if (song.Sections is null || song.Sections.Length is 0 or > 50) throw new InvalidDataException("Invalid section count.");
        double secondsPerTick = 60.0 / (song.BeatsPerMinute * song.TicksPerBeat);
        var blocks = song.Sections.Select(s =>
        {
            int last = Math.Max(s.Melody.Length == 0 ? 0 : s.Melody.Max(n => checked(n.StartTick + n.DurationTicks)), s.Chords.Length * song.TicksPerBeat * 4);
            if (last < 0) throw new InvalidDataException("Negative timeline.");
            return (section:s, length:Math.Max(last, song.TicksPerBeat * 4));
        }).ToArray();
        long frames = blocks.Sum(b => (long)Math.Ceiling(b.length * secondsPerTick * SampleRate)) + SampleRate;
        if (frames > SampleRate * 60L * 15) throw new InvalidDataException("Arrangement exceeds 15-minute safety limit.");
        var target = Path.GetFullPath(path);
        Directory.CreateDirectory(Path.GetDirectoryName(target)!);
        var temp = target + "." + Guid.NewGuid().ToString("N") + ".tmp";
        try
        {
            using (var fs = new FileStream(temp, FileMode.CreateNew, FileAccess.Write, FileShare.None, 65536))
            using (var bw = new BinaryWriter(fs, Encoding.ASCII, leaveOpen:true))
            {
                long bytes = frames * 4;
                if (bytes > uint.MaxValue - 44) throw new InvalidDataException("Wave file exceeds RIFF limit.");
                bw.Write("RIFF"u8); bw.Write((uint)(36 + bytes)); bw.Write("WAVEfmt "u8);
                bw.Write(16); bw.Write((short)1); bw.Write((short)2); bw.Write(SampleRate);
                bw.Write(SampleRate * 4); bw.Write((short)4); bw.Write((short)16);
                bw.Write("data"u8); bw.Write((uint)bytes);
                long offset = 0;
                foreach (var (section, length) in blocks)
                {
                    cancellation.ThrowIfCancellationRequested();
                    long count = (long)Math.Ceiling(length * secondsPerTick * SampleRate);
                    foreach (var blockStart in Enumerable.Range(0, checked((int)((count + 4095) / 4096))))
                    {
                        cancellation.ThrowIfCancellationRequested();
                        int size = (int)Math.Min(4096, count - blockStart * 4096L);
                        var buffer = new byte[size * 4];
                        for (int i = 0; i < size; i++)
                        {
                            double t = (blockStart * 4096L + i) / (double)SampleRate;
                            double tick = t / secondsPerTick;
                            double melody = 0;
                            foreach (var note in section.Melody)
                            {
                                if (note.Pitch is < 0 or > 127 || note.StartTick < 0 || note.DurationTicks <= 0) throw new InvalidDataException("Invalid melody note.");
                                double start = note.StartTick * secondsPerTick, end = (note.StartTick + note.DurationTicks) * secondsPerTick;
                                if (t < start || t >= end) continue;
                                double age = t - start;
                                double envelope = Math.Min(1, age * 30) * Math.Min(1, (end - t) * 14);
                                double hz = 440 * Math.Pow(2, (note.Pitch - 69) / 12.0);
                                melody += (Math.Sin(2 * Math.PI * hz * age) + 0.28 * Math.Sin(4 * Math.PI * hz * age)) * envelope * .19;
                            }
                            int chordIndex = Math.Min(section.Chords.Length - 1, (int)(tick / (song.TicksPerBeat * 4)));
                            int root = chordIndex >= 0 ? Root(section.Chords[chordIndex]) : 48;
                            double beat = t * song.BeatsPerMinute / 60;
                            double pad = 0;
                            foreach (int shift in new[] { 0, 4, 7 })
                            {
                                double f = 440 * Math.Pow(2, (root + 12 + shift - 69) / 12.0);
                                pad += Math.Sin(2 * Math.PI * f * t) * 0.033;
                            }
                            double bassHz = 440 * Math.Pow(2, (root - 69) / 12.0);
                            double bass = Math.Sin(2 * Math.PI * bassHz * t) * .12;
                            double beatPhase = beat - Math.Floor(beat);
                            double kick = Math.Exp(-beatPhase * 35) * Math.Sin(2 * Math.PI * (75 - 30 * beatPhase) * t) * .22;
                            double snarePhase = (beat + 0.5) - Math.Floor(beat + 0.5);
                            double noise = HashNoise(offset + blockStart * 4096L + i);
                            double snare = Math.Exp(-snarePhase * 42) * noise * .07;
                            double v = Math.Tanh((melody + pad + bass + kick + snare) * .88);
                            short pcm = (short)Math.Clamp((int)Math.Round(v * 32760), -32768, 32767);
                            int at = i * 4;
                            buffer[at] = (byte)pcm; buffer[at + 1] = (byte)(pcm >> 8);
                            buffer[at + 2] = (byte)pcm; buffer[at + 3] = (byte)(pcm >> 8);
                        }
                        bw.Write(buffer);
                    }
                    offset += count;
                }
                long remaining = frames - offset;
                var silence = new byte[4096 * 4];
                while (remaining > 0) { int n = (int)Math.Min(4096, remaining); bw.Write(silence, 0, n * 4); remaining -= n; }
            }
            File.Move(temp, target, overwrite:true);
        }
        finally { if (File.Exists(temp)) File.Delete(temp); }
    }
    private static int Root(string chord)
    {
        if (string.IsNullOrWhiteSpace(chord)) return 48;
        int note = char.ToUpperInvariant(chord[0]) switch { 'C'=>48, 'D'=>50, 'E'=>52, 'F'=>53, 'G'=>55, 'A'=>57, 'B'=>59, _=>48 };
        if (chord.Length > 1 && chord[1] == '#') note++; else if (chord.Length > 1 && chord[1] == 'b') note--;
        return note;
    }
    private static double HashNoise(long i)
    {
        unchecked { ulong x = (ulong)i * 0x9e3779b97f4a7c15UL; x ^= x >> 30; x *= 0xbf58476d1ce4e5b9UL; x ^= x >> 27; return (x >> 11) / (double)(1UL << 53) * 2 - 1; }
    }
}
