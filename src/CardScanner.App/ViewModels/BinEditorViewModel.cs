using System.Collections.ObjectModel;
using System.Globalization;
using CardScanner.Core.Sorting;
using CommunityToolkit.Mvvm.ComponentModel;
using CommunityToolkit.Mvvm.Input;

namespace CardScanner.App.ViewModels;

/// <summary>A toggle in a bin's rule (a colour, a rarity, a card type).</summary>
public partial class RuleOption : ObservableObject
{
    public string Code { get; }
    public string Text { get; }
    private readonly Action _changed;
    [ObservableProperty] private bool _isOn;
    public RuleOption(string code, string text, Action changed) { Code = code; Text = text; _changed = changed; }
    partial void OnIsOnChanged(bool value) => _changed();
}

/// <summary>One bin in the picture of the machine, and the rule it's edited with.</summary>
public partial class BinSlot : ObservableObject
{
    public static readonly string[] KindList = ["Empty (takes nothing)", "Price range", "Color", "Name starts with", "Rarity", "Set", "Card type", "Everything else"];
    private static readonly RuleKind?[] KindOf = [null, RuleKind.Price, RuleKind.Color, RuleKind.Letters, RuleKind.Rarity, RuleKind.Set, RuleKind.Type, RuleKind.Anything];

    private readonly BinEditorViewModel _owner;
    private bool _loading;
    public int Bin { get; }
    public string Title => $"Bin {Bin}";
    /// <summary>Bin 9 only ever exists as the end of the line.</summary>
    public bool CanHaveRule => Bin < BinSetup.MaxBins;

    [ObservableProperty] private bool _isOff;
    [ObservableProperty] private bool _isEnd;
    [ObservableProperty] private bool _isSelected;
    [ObservableProperty] private string _summary = "";
    [ObservableProperty] private string _role = "";

    [ObservableProperty] private string _kind = KindList[0];
    [ObservableProperty] private string _name = "";
    [ObservableProperty] private string _minText = "";
    [ObservableProperty] private string _maxText = "";
    [ObservableProperty] private string _letters = "";
    [ObservableProperty] private string _setsText = "";
    public ObservableCollection<RuleOption> Colors { get; } = [];
    public ObservableCollection<RuleOption> Rarities { get; } = [];
    public ObservableCollection<RuleOption> Types { get; } = [];

    public bool IsPrice => Kind == KindList[1];
    public bool IsColor => Kind == KindList[2];
    public bool IsLetters => Kind == KindList[3];
    public bool IsRarity => Kind == KindList[4];
    public bool IsSet => Kind == KindList[5];
    public bool IsType => Kind == KindList[6];
    public bool IsAnything => Kind == KindList[7];
    public bool IsEmpty => Kind == KindList[0];
    /// <summary>The rule editor shows (not the end bin).</summary>
    public bool ShowRule => !IsEnd && CanHaveRule;

    public BinSlot(BinEditorViewModel owner, int bin)
    {
        _owner = owner;
        Bin = bin;
        for (int i = 0; i < BinRule.ColorCodes.Length; i++) Colors.Add(new RuleOption(BinRule.ColorCodes[i], BinRule.ColorNames[i], Changed));
        foreach (var r in BinRule.RarityCodes) Rarities.Add(new RuleOption(r, r == "special" ? "Special / bonus" : char.ToUpperInvariant(r[0]) + r[1..], Changed));
        foreach (var t in BinRule.TypeNames) Types.Add(new RuleOption(t, t, Changed));
    }

    partial void OnKindChanged(string value)
    {
        foreach (var p in new[] { nameof(IsPrice), nameof(IsColor), nameof(IsLetters), nameof(IsRarity), nameof(IsSet), nameof(IsType), nameof(IsAnything), nameof(IsEmpty) })
            OnPropertyChanged(p);
        Changed();
    }
    partial void OnNameChanged(string value) => Changed();
    partial void OnMinTextChanged(string value) => Changed();
    partial void OnMaxTextChanged(string value) => Changed();
    partial void OnLettersChanged(string value) => Changed();
    partial void OnSetsTextChanged(string value) => Changed();
    partial void OnIsEndChanged(bool value) => OnPropertyChanged(nameof(ShowRule));

    private void Changed()
    {
        if (_loading) return;
        Refresh();
        _owner.SlotChanged();
    }

    internal void Refresh()
    {
        Summary = IsEnd ? "Flagged + everything else" : !CanHaveRule ? "End bin only" : ToRule()?.Label ?? "Empty";
        Role = IsOff ? "off" : IsEnd ? "end of the line" : Bin == 1 ? "first door" : "door";
    }

    public void Load(BinRule? r)
    {
        _loading = true;
        Kind = r is null ? KindList[0] : KindList[Array.IndexOf(KindOf, r.Kind)];
        Name = r?.Name ?? "";
        MinText = r?.Min?.ToString("0.##", CultureInfo.InvariantCulture) ?? "";
        MaxText = r?.Max?.ToString("0.##", CultureInfo.InvariantCulture) ?? "";
        Letters = r?.Letters ?? "";
        SetsText = r is null ? "" : string.Join(", ", r.Sets);
        foreach (var o in Colors) o.IsOn = r?.Colors.Contains(o.Code) == true;
        foreach (var o in Rarities) o.IsOn = r?.Rarities.Contains(o.Code) == true;
        foreach (var o in Types) o.IsOn = r?.Types.Contains(o.Code) == true;
        _loading = false;
        Refresh();
    }

    public BinRule? ToRule()
    {
        int k = Array.IndexOf(KindList, Kind);
        if (k <= 0 || KindOf[k] is not { } kind) return null;
        static decimal? Dollars(string t) =>
            decimal.TryParse(t.Trim().TrimStart('$'), NumberStyles.Number, CultureInfo.InvariantCulture, out var d) && d >= 0 ? d : null;
        return new BinRule
        {
            Kind = kind,
            Name = Name.Trim(),
            Min = Dollars(MinText),
            Max = Dollars(MaxText),
            Letters = Letters.Trim(),
            Sets = SetsText.Split([',', ' ', ';', '/', '\n'], StringSplitOptions.RemoveEmptyEntries | StringSplitOptions.TrimEntries)
                           .Select(s => s.ToUpperInvariant()).Distinct().ToList(),
            Colors = Colors.Where(o => o.IsOn).Select(o => o.Code).ToList(),
            Rarities = Rarities.Where(o => o.IsOn).Select(o => o.Code).ToList(),
            Types = Types.Where(o => o.IsOn).Select(o => o.Code).ToList(),
        };
    }
}

/// <summary>
/// The bin setup as a picture of the machine: 9 bins from the feeder to the end. Click a bin to set what it
/// takes. Used by the Start session panel and the Settings page.
/// </summary>
public partial class BinEditorViewModel : ObservableObject
{
    public static readonly int[] BinCountList = [2, 3, 4, 5, 6, 7, 8, 9];
    public static readonly string[] PresetList = ["Price brackets", "Color", "Alphabetical", "Rarity", "Set (keeps your set lists)"];

    public ObservableCollection<BinSlot> Slots { get; } = [];
    [ObservableProperty] private int _binsInUse = 3;
    [ObservableProperty] private BinSlot? _selected;
    [ObservableProperty] private string _preset = PresetList[0];
    private BinSetup _base = new();
    private bool _loading;
    private UiSettings? _store;

    // ---- saved setups ("★ Save these bins as…"), the same as on the machine's touchscreen
    public ObservableCollection<string> SavedNames { get; } = [];
    [ObservableProperty] private string? _savedPick;
    [ObservableProperty] private string _saveName = "";
    [ObservableProperty] private string _savedText = "";
    public bool HasSaved => SavedNames.Count > 0;

    /// <summary>Where saved setups are kept (the app's settings).</summary>
    public void AttachStore(UiSettings store)
    {
        _store = store;
        RefreshSaved();
    }

    private void RefreshSaved()
    {
        var pick = SavedPick;
        SavedNames.Clear();
        foreach (var x in _store?.SavedSetups ?? []) SavedNames.Add(x.Name);
        SavedPick = SavedNames.Contains(pick ?? "") ? pick : null;
        OnPropertyChanged(nameof(HasSaved));
    }

    /// <summary>Picking a saved setup loads it straight away (like tapping it on the machine).</summary>
    partial void OnSavedPickChanged(string? value)
    {
        var x = _store?.SavedSetups.FirstOrDefault(s => s.Name == value);
        if (x is null) return;
        Load(x.Setup.Clone());
        SaveName = x.Name;
        SavedText = $"Loaded “{x.Name}”.";
        Changed?.Invoke();
    }

    [RelayCommand]
    private void SaveAs()
    {
        if (_store is null) return;
        var name = SaveName.Trim();
        if (name.Length == 0) name = "My setup";
        _store.SavedSetups.RemoveAll(s => s.Name == name);
        _store.SavedSetups.Insert(0, new NamedSetup { Name = name, Setup = ToSetup() });
        if (_store.SavedSetups.Count > 12) _store.SavedSetups.RemoveRange(12, _store.SavedSetups.Count - 12);
        _store.Save();
        RefreshSaved();
        SavedText = $"★ Saved as “{name}”.";
    }

    [RelayCommand]
    private void DeleteSaved()
    {
        if (_store is null || SavedPick is not { } name) return;
        _store.SavedSetups.RemoveAll(s => s.Name == name);
        _store.Save();
        SavedPick = null;
        RefreshSaved();
        SavedText = $"Deleted “{name}”.";
    }

    /// <summary>Raised whenever anything changes (the Settings page shows "not saved yet").</summary>
    public event Action? Changed;

    public BinEditorViewModel()
    {
        for (int b = 1; b <= BinSetup.MaxBins; b++) Slots.Add(new BinSlot(this, b));
        Load(new BinSetup());
    }

    public bool SelectedIsOff => Selected?.IsOff == true;
    public string SelectedHeader => Selected is not { } s ? "" : $"Bin {s.Bin} · {s.Role}";
    public string TurnOnText => Selected is { } s ? $"Use bins 1–{s.Bin}" : "";

    partial void OnSelectedChanged(BinSlot? oldValue, BinSlot? newValue)
    {
        if (oldValue is not null) oldValue.IsSelected = false;
        if (newValue is not null) newValue.IsSelected = true;
        OnPropertyChanged(nameof(SelectedIsOff));
        OnPropertyChanged(nameof(SelectedHeader));
        OnPropertyChanged(nameof(TurnOnText));
    }

    partial void OnBinsInUseChanged(int value)
    {
        UpdateRoles();
        if (!_loading) Changed?.Invoke();
    }

    private void UpdateRoles()
    {
        int n = Math.Clamp(BinsInUse, 2, BinSetup.MaxBins);
        foreach (var s in Slots)
        {
            s.IsOff = s.Bin > n;
            s.IsEnd = s.Bin == n;
            s.Refresh();
        }
        OnPropertyChanged(nameof(SelectedIsOff));
        OnPropertyChanged(nameof(SelectedHeader));
    }

    [RelayCommand] private void Select(BinSlot? slot) => Selected = slot;

    [RelayCommand]
    private void TurnOnUpTo()
    {
        if (Selected is { } s) BinsInUse = s.Bin;
    }

    [RelayCommand]
    private void ApplyPreset()
    {
        var setup = ToSetup();
        int i = Array.IndexOf(PresetList, Preset);
        setup.ApplyPreset(i switch { 1 => SortBy.Color, 2 => SortBy.Alphabet, 3 => SortBy.Rarity, 4 => SortBy.Set, _ => SortBy.Price });
        Load(setup);
        Changed?.Invoke();
    }

    internal void SlotChanged() => Changed?.Invoke();

    public void Load(BinSetup setup)
    {
        _loading = true;
        _base = setup.Clone();
        var rules = setup.EffectiveRules();
        BinsInUse = Math.Clamp(setup.BinsInUse, 2, BinSetup.MaxBins);
        foreach (var s in Slots) s.Load(s.CanHaveRule ? rules[s.Bin - 1] : null);
        UpdateRoles();
        _loading = false;
        Selected ??= Slots[0];
    }

    public BinSetup ToSetup()
    {
        var s = _base.Clone();
        s.BinsInUse = Math.Clamp(BinsInUse, 2, BinSetup.MaxBins);
        s.Rules = [.. Slots.Where(x => x.CanHaveRule).Select(x => x.ToRule())];
        // set lists typed in Set bins are remembered for the Set preset
        var sets = s.Rules.Where(r => r?.Kind == RuleKind.Set).Select(r => string.Join(", ", r!.Sets)).Where(g => g.Length > 0).ToList();
        if (sets.Count > 0) s.SetGroups = sets;
        return s;
    }
}
