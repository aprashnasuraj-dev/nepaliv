using NepaliV.Studio.Domain;
namespace NepaliV.Studio.Generation;
/// <summary>Original curated offline phrases. Limited repertoire; not generative neural poetry.</summary>
public static class OfflineLyricWriter
{
    private static readonly string[][] Nepali = [
      ["टाढा छ घर, नजिक छ सम्झना", "हावाले ल्यायो आँगनको खबर", "आँखामा बस्छ पुरानो त्यो बाटो", "मनले खोज्छ आफ्नै घर"],
      ["साँझले सोध्यो किन चुप छु आज", "ताराले टिप्यो नभनेको राज", "एक्लो यो बाटो लामो भए पनि", "तिम्रो उज्यालो बन्यो आवाज"],
      ["पहाडको छायाँ तल झरेपछि", "चौतारीमा पुरानो गीत बजेपछि", "हातका रेखा कहाँ छुटे होलान्", "सम्झनाका फूल फेरि फुलेपछि"],
      ["भोलिको घाम बोकी आउँछु म", "यो मनको कुरा सुनाउन आउँछु म", "दूरीले हाम्रो माया मेट्दैन", "नयाँ बिहान सजाउन आउँछु म"]
    ];
    private static readonly string[][] Hindi = [
      ["दूर है घर, पास उसकी याद", "हवा में सुनता हूँ कोई फ़रियाद", "रास्तों से पूछूँ कहाँ है सवेरा", "दिल में अब भी जलती उम्मीद की बात"],
      ["खिड़की पर ठहरी बरसात की रात", "दिल में रह गई अधूरी सी बात", "रौशनी ढूँढूँ हर एक अँधेरे में", "तेरी हँसी देती फिर से साथ"],
      ["धीमे से मौसम ने दरवाज़ा खोला", "बीते हुए कल ने कुछ मुझसे बोला", "चुपके से सपनों को फिर से सँवारा", "दिल ने नया रास्ता चुनकर टटोला"],
      ["आएगी सुबह, ये वादा रहा", "रास्ता चाहे कितना भी तन्हा रहा", "हम फिर मिलेंगे किसी मोड़ पर", "हर धड़कन में ये सपना रहा"]
    ];
    public static string[] Compose(CreativeBrief brief, string role, int take)
    {
       var verses = brief.Language == SongLanguage.Nepali ? Nepali : Hindi;
       int index = role.Contains("Chorus", StringComparison.OrdinalIgnoreCase) ? 3 :
           role.Contains("Bridge", StringComparison.OrdinalIgnoreCase) ? 2 :
           role.Contains("Pre", StringComparison.OrdinalIgnoreCase) ? 1 : take % 3;
       string[] lines = (string[])verses[index].Clone();
       if (role.Contains("Chorus", StringComparison.OrdinalIgnoreCase)) return [lines[0], lines[2], lines[0], lines[3]];
       if (role is "Intro" or "Outro") return [lines[0], lines[3]];
       int offset = take % lines.Length;
       return lines.Skip(offset).Concat(lines.Take(offset)).ToArray();
    }
}