namespace NepaliV.Studio.Domain;

/// <summary>The exportable, provider-independent creative source of truth.</summary>
public sealed record CreativeBrief(string Intent, SongLanguage Language, string Tradition, int Modernity, int Seed);
public enum SongLanguage { Nepali, Hindi }
public sealed record NoteEvent(int Pitch, int StartTick, int DurationTicks, string? Syllable = null);
public sealed record SongSection(Guid Id, string Role, string[] Lines, string[] Chords, NoteEvent[] Melody);
public sealed record SongDocument(Guid Id, int Revision, string Title, CreativeBrief Brief, int BeatsPerMinute, int TicksPerBeat, SongSection[] Sections, string Provider, DateTimeOffset CreatedUtc);
