using System.IO;
using System.Text;
using System.Text.Json;
using System.Windows;
using System.Windows.Controls;
using Microsoft.Win32;
using NepaliV.Studio.Domain;
using NepaliV.Studio.Generation;
using NepaliV.Studio.Export;

namespace NepaliV.Studio;
public partial class MainWindow : Window
{
    private readonly OfflineSketchGenerator _generator = new();
    private readonly List<SongDocument> _takes = [];
    public MainWindow() => InitializeComponent();
    private async void Generate_Click(object sender, RoutedEventArgs e)
    {
        try
        {
            var brief = new CreativeBrief(Intent.Text.Trim(), SongLanguagePicker.SelectedIndex == 1 ? SongLanguage.Hindi : SongLanguage.Nepali,
                (Tradition.SelectedItem as ComboBoxItem)?.Content?.ToString() ?? "Adhunik", (int)Modernity.Value, Environment.TickCount);
            Status.Text = "Composing local symbolic sketches…";
            var results = await Task.Run(() => Enumerable.Range(0, 3).Select(i => _generator.Generate(brief, i)).ToArray());
            _takes.Clear(); _takes.AddRange(results); Takes.ItemsSource = null;
            Takes.ItemsSource = _takes.Select(t => t.Title).ToArray(); Takes.SelectedIndex = 0;
            Status.Text = "Three independent symbolic sketches. Lyrics are editable placeholders, not AI-authored poetry.";
        }
        catch (Exception ex) { MessageBox.Show(this, ex.Message, "Generation error", MessageBoxButton.OK, MessageBoxImage.Warning); Status.Text = "Generation failed."; }
    }
    private SongDocument? Selected => Takes.SelectedIndex >= 0 && Takes.SelectedIndex < _takes.Count ? _takes[Takes.SelectedIndex] : null;
    private void Takes_SelectionChanged(object sender, SelectionChangedEventArgs e)
    {
        if (Selected is not { } s) { Score.Text = ""; return; }
        var sb = new StringBuilder();
        sb.AppendLine($"{s.Title}  ·  {s.BeatsPerMinute} BPM  ·  {s.Brief.Language}");
        sb.AppendLine($"DNA: {s.Brief.Tradition}, modernity {s.Brief.Modernity}%");
        foreach (var part in s.Sections)
        {
            sb.AppendLine().AppendLine($"── {part.Role} ──");
            sb.AppendLine(string.Join("  ·  ", part.Chords));
            foreach (string line in part.Lines) sb.AppendLine(line);
        }
        Score.Text = sb.ToString();
    }
    private void Save_Click(object sender, RoutedEventArgs e)
    {
        if (Selected is not { } song) { Status.Text = "Generate a sketch first."; return; }
        var dialog = new SaveFileDialog { Filter = "NepaliV project (*.json)|*.json", FileName = "NepaliV-song.json" };
        if (dialog.ShowDialog() != true) return;
        try { File.WriteAllText(dialog.FileName, JsonSerializer.Serialize(song, new JsonSerializerOptions { WriteIndented = true }), Encoding.UTF8); Status.Text = "Project saved."; }
        catch (Exception ex) { MessageBox.Show(this, ex.Message, "Save error"); }
    }
    private void Midi_Click(object sender, RoutedEventArgs e)
    {
        if (Selected is not { } song) { Status.Text = "Generate a sketch first."; return; }
        var dialog = new SaveFileDialog { Filter = "Standard MIDI (*.mid)|*.mid", FileName = "NepaliV-melody.mid" };
        if (dialog.ShowDialog() != true) return;
        try { MidiExporter.Write(song, dialog.FileName); Status.Text = "MIDI exported. Import into a DAW and assign instruments."; }
        catch (Exception ex) { MessageBox.Show(this, ex.Message, "MIDI export error"); }
    }
}
