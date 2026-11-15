using System.Drawing.Imaging;

namespace FennsillPreview;

static class ScreenFace
{
    public const int Width = 800;
    public const int Height = 480;

    static readonly Dictionary<char, string[]> Glyphs = new()
    {
        [' '] = [".....", ".....", ".....", ".....", ".....", ".....", "....."],
        ['A'] = [".###.", "#...#", "#...#", "#####", "#...#", "#...#", "#...#"],
        ['B'] = ["####.", "#...#", "#...#", "####.", "#...#", "#...#", "####."],
        ['C'] = [".###.", "#...#", "#....", "#....", "#....", "#...#", ".###."],
        ['D'] = ["####.", "#...#", "#...#", "#...#", "#...#", "#...#", "####."],
        ['E'] = ["#####", "#....", "#....", "####.", "#....", "#....", "#####"],
        ['F'] = ["#####", "#....", "#....", "####.", "#....", "#....", "#...."],
        ['G'] = [".###.", "#...#", "#....", "#.###", "#...#", "#...#", ".###."],
        ['H'] = ["#...#", "#...#", "#...#", "#####", "#...#", "#...#", "#...#"],
        ['I'] = ["#####", "..#..", "..#..", "..#..", "..#..", "..#..", "#####"],
        ['J'] = ["..###", "...#.", "...#.", "...#.", "#..#.", "#..#.", ".##.."],
        ['K'] = ["#...#", "#..#.", "#.#..", "##...", "#.#..", "#..#.", "#...#"],
        ['L'] = ["#....", "#....", "#....", "#....", "#....", "#....", "#####"],
        ['M'] = ["#...#", "##.##", "#.#.#", "#...#", "#...#", "#...#", "#...#"],
        ['N'] = ["#...#", "##..#", "#.#.#", "#..##", "#...#", "#...#", "#...#"],
        ['O'] = [".###.", "#...#", "#...#", "#...#", "#...#", "#...#", ".###."],
        ['P'] = ["####.", "#...#", "#...#", "####.", "#....", "#....", "#...."],
        ['Q'] = [".###.", "#...#", "#...#", "#...#", "#.#.#", "#..#.", ".##.#"],
        ['R'] = ["####.", "#...#", "#...#", "####.", "#.#..", "#..#.", "#...#"],
        ['S'] = [".####", "#....", "#....", ".###.", "....#", "....#", "####."],
        ['T'] = ["#####", "..#..", "..#..", "..#..", "..#..", "..#..", "..#.."],
        ['U'] = ["#...#", "#...#", "#...#", "#...#", "#...#", "#...#", ".###."],
        ['V'] = ["#...#", "#...#", "#...#", "#...#", "#...#", ".#.#.", "..#.."],
        ['W'] = ["#...#", "#...#", "#...#", "#.#.#", "#.#.#", "##.##", "#...#"],
        ['X'] = ["#...#", "#...#", ".#.#.", "..#..", ".#.#.", "#...#", "#...#"],
        ['Y'] = ["#...#", "#...#", ".#.#.", "..#..", "..#..", "..#..", "..#.."],
        ['Z'] = ["#####", "....#", "...#.", "..#..", ".#...", "#....", "#####"],
        ['0'] = [".###.", "#...#", "#..##", "#.#.#", "##..#", "#...#", ".###."],
        ['1'] = ["..#..", ".##..", "..#..", "..#..", "..#..", "..#..", ".###."],
        ['2'] = [".###.", "#...#", "....#", "...#.", "..#..", ".#...", "#####"],
        ['3'] = ["####.", "....#", "....#", ".###.", "....#", "....#", "####."],
        ['4'] = ["...#.", "..##.", ".#.#.", "#..#.", "#####", "...#.", "...#."],
        ['5'] = ["#####", "#....", "#....", "####.", "....#", "....#", "####."],
        ['6'] = [".###.", "#....", "#....", "####.", "#...#", "#...#", ".###."],
        ['7'] = ["#####", "....#", "...#.", "..#..", ".#...", ".#...", ".#..."],
        ['8'] = [".###.", "#...#", "#...#", ".###.", "#...#", "#...#", ".###."],
        ['9'] = [".###.", "#...#", "#...#", ".####", "....#", "....#", ".###."],
        ['.'] = [".....", ".....", ".....", ".....", ".....", ".##..", ".##.."],
        ['+'] = [".....", "..#..", "..#..", "#####", "..#..", "..#..", "....."],
        ['-'] = [".....", ".....", ".....", "#####", ".....", ".....", "....."],
        ['%'] = ["##..#", "##..#", "...#.", "..#..", ".#...", "#..##", "#..##"],
        [':'] = [".....", ".##..", ".##..", ".....", ".##..", ".##..", "....."],
    };

    public static Bitmap Content(string title, IEnumerable<string> lines)
    {
        var page = Blank();
        Fill(page, 0, 0, Width, 64, black: true);
        Text(page, Cut(title, 22), 28, 16, 4, black: false);
        var y = 92;
        foreach (var line in lines)
        {
            if (string.IsNullOrWhiteSpace(line) || y > 440) continue;
            Text(page, Cut(line, 36), 28, y, 4, black: true);
            y += 40;
        }
        return ToBitmap(page);
    }

    public static Bitmap UpdateQuestion(string version)
    {
        var page = Blank();
        Text(page, "SOFTWARE UPDATE", 24, 70, 3, black: true);
        Text(page, Cut(version, 22), 24, 130, 3, black: true);
        Text(page, "BOOT INSTALLS IT", 24, 210, 2, black: true);
        Text(page, "LEAVE IT TO SKIP", 24, 246, 2, black: true);
        return ToBitmap(page);
    }

    static string Cut(string text, int max)
    {
        var upper = (text ?? "").Trim().ToUpperInvariant();
        return upper.Length <= max ? upper : upper[..max];
    }

    static byte[] Blank()
    {
        var page = new byte[Width * Height];
        Array.Fill(page, (byte)255);
        return page;
    }

    static void Fill(byte[] page, int x, int y, int w, int h, bool black)
    {
        var ink = (byte)(black ? 0 : 255);
        for (var yy = y; yy < y + h; yy++)
        {
            if (yy < 0 || yy >= Height) continue;
            for (var xx = x; xx < x + w; xx++)
            {
                if (xx < 0 || xx >= Width) continue;
                page[yy * Width + xx] = ink;
            }
        }
    }

    static void Text(byte[] page, string text, int x, int y, int scale, bool black)
    {
        var cursor = x;
        foreach (var ch in text)
        {
            if (!Glyphs.TryGetValue(ch, out var glyph)) glyph = Glyphs[' '];
            for (var row = 0; row < glyph.Length; row++)
            {
                var bits = glyph[row];
                for (var col = 0; col < bits.Length; col++)
                {
                    if (bits[col] != '#') continue;
                    Fill(page, cursor + col * scale, y + row * scale, scale, scale, black);
                }
            }
            cursor += 6 * scale;
        }
    }

    static Bitmap ToBitmap(byte[] page)
    {
        var bmp = new Bitmap(Width, Height, PixelFormat.Format24bppRgb);
        var data = bmp.LockBits(new Rectangle(0, 0, Width, Height), ImageLockMode.WriteOnly, PixelFormat.Format24bppRgb);
        try
        {
            var stride = data.Stride;
            var raw = new byte[stride * Height];
            for (var y = 0; y < Height; y++)
            {
                for (var x = 0; x < Width; x++)
                {
                    var value = page[y * Width + x];
                    var at = y * stride + x * 3;
                    raw[at] = value;
                    raw[at + 1] = value;
                    raw[at + 2] = value;
                }
            }
            System.Runtime.InteropServices.Marshal.Copy(raw, 0, data.Scan0, raw.Length);
        }
        finally
        {
            bmp.UnlockBits(data);
        }
        return bmp;
    }
}
