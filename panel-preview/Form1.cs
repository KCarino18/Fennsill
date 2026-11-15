namespace FennsillPreview;

public partial class Form1 : Form
{
    readonly TextBox _title = new();
    readonly TextBox _lines = new();
    readonly PictureBox _screen = new();
    Bitmap? _face;

    public Form1()
    {
        InitializeComponent();
        Build();
        ShowContent();
    }

    void Build()
    {
        Text = "Fennsill panel";
        BackColor = Color.FromArgb(216, 212, 204);
        FormBorderStyle = FormBorderStyle.FixedSingle;
        MaximizeBox = false;
        StartPosition = FormStartPosition.CenterScreen;
        Font = new Font("Segoe UI", 11F);

        const int screenW = ScreenFace.Width;
        const int screenH = ScreenFace.Height;

        var caption = new Label
        {
            AutoSize = true,
            Text = "Picture of the 800 x 480 panel. This window does not connect to the board.",
            ForeColor = Color.FromArgb(34, 34, 34),
            Location = new Point(20, 16),
        };

        var titleLabel = new Label { AutoSize = true, Text = "Title", Location = new Point(20, 48) };
        _title.Text = "Today";
        _title.Location = new Point(70, 44);
        _title.Width = 180;

        var linesLabel = new Label { AutoSize = true, Text = "Lines", Location = new Point(266, 48) };
        _lines.Multiline = true;
        _lines.ScrollBars = ScrollBars.Vertical;
        _lines.Text = "Dentist at 3" + Environment.NewLine + "Buy milk";
        _lines.Location = new Point(320, 44);
        _lines.Size = new Size(280, 56);

        var mine = new Button { Text = "My screen", Location = new Point(616, 44), Size = new Size(110, 32) };
        var update = new Button { Text = "Update question", Location = new Point(736, 44), Size = new Size(150, 32) };
        mine.Click += (_, _) => ShowContent();
        update.Click += (_, _) => ShowUpdate();
        _title.TextChanged += (_, _) => ShowContent();
        _lines.TextChanged += (_, _) => ShowContent();

        var bezel = new Panel
        {
            BackColor = Color.FromArgb(17, 17, 17),
            Location = new Point(20, 112),
            Size = new Size(screenW + 28, screenH + 28),
            Padding = new Padding(14),
        };
        _screen.Location = new Point(14, 14);
        _screen.Size = new Size(screenW, screenH);
        _screen.SizeMode = PictureBoxSizeMode.Normal;
        bezel.Controls.Add(_screen);

        Controls.Add(caption);
        Controls.Add(titleLabel);
        Controls.Add(_title);
        Controls.Add(linesLabel);
        Controls.Add(_lines);
        Controls.Add(mine);
        Controls.Add(update);
        Controls.Add(bezel);

        ClientSize = new Size(Math.Max(bezel.Right, update.Right) + 20, bezel.Bottom + 20);
    }

    void ShowContent()
    {
        var lines = _lines.Text.Replace("\r\n", "\n").Replace('\r', '\n').Split('\n');
        Swap(ScreenFace.Content(_title.Text, lines));
    }

    void ShowUpdate()
    {
        Swap(ScreenFace.UpdateQuestion("1.1.0"));
    }

    void Swap(Bitmap next)
    {
        var previous = _face;
        _face = next;
        _screen.Image = next;
        previous?.Dispose();
    }
}
