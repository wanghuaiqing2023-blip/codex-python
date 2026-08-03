use serde::Serialize;
use syntect::easy::HighlightLines;
use syntect::highlighting::{FontStyle, Highlighter, Style, Theme};
use syntect::parsing::Scope;
use syntect::util::LinesWithEndings;
use two_face::theme::{self, EmbeddedLazyThemeSet, EmbeddedThemeName};

const CORPUS: &str = r#"fn demo(parameter: &[Widget]) -> String {
    // comment role
    let variable: Vec<&str> = Widget::method(42);
    let filtered = items.iter().filter(|candidate| candidate.ready).count();
    format!("{variable} text {}", parameter.value())
}"#;

#[derive(Serialize)]
struct ProbeStyle {
    r: u8,
    g: u8,
    b: u8,
    a: u8,
    bold: bool,
}

#[derive(Serialize)]
struct ProbeSpan {
    text: String,
    style: ProbeStyle,
}

#[derive(Serialize)]
struct ThemeProbe {
    name: &'static str,
    inserted_background: Option<[u8; 3]>,
    deleted_background: Option<[u8; 3]>,
    lines: Vec<Vec<ProbeSpan>>,
}

fn scope_background(theme: &Theme, primary: &str, fallback: &str) -> Option<[u8; 3]> {
    let highlighter = Highlighter::new(theme);
    [primary, fallback].into_iter().find_map(|name| {
        let scope = Scope::new(name).ok()?;
        let color = highlighter.style_mod_for_stack(&[scope]).background?;
        Some([color.r, color.g, color.b])
    })
}

fn canonical_name(name: EmbeddedThemeName) -> &'static str {
    match name {
        EmbeddedThemeName::Ansi => "ansi",
        EmbeddedThemeName::Base16 => "base16",
        EmbeddedThemeName::Base16EightiesDark => "base16-eighties-dark",
        EmbeddedThemeName::Base16MochaDark => "base16-mocha-dark",
        EmbeddedThemeName::Base16OceanDark => "base16-ocean-dark",
        EmbeddedThemeName::Base16OceanLight => "base16-ocean-light",
        EmbeddedThemeName::Base16_256 => "base16-256",
        EmbeddedThemeName::CatppuccinFrappe => "catppuccin-frappe",
        EmbeddedThemeName::CatppuccinLatte => "catppuccin-latte",
        EmbeddedThemeName::CatppuccinMacchiato => "catppuccin-macchiato",
        EmbeddedThemeName::CatppuccinMocha => "catppuccin-mocha",
        EmbeddedThemeName::ColdarkCold => "coldark-cold",
        EmbeddedThemeName::ColdarkDark => "coldark-dark",
        EmbeddedThemeName::DarkNeon => "dark-neon",
        EmbeddedThemeName::Dracula => "dracula",
        EmbeddedThemeName::Github => "github",
        EmbeddedThemeName::GruvboxDark => "gruvbox-dark",
        EmbeddedThemeName::GruvboxLight => "gruvbox-light",
        EmbeddedThemeName::InspiredGithub => "inspired-github",
        EmbeddedThemeName::Leet => "1337",
        EmbeddedThemeName::MonokaiExtended => "monokai-extended",
        EmbeddedThemeName::MonokaiExtendedBright => "monokai-extended-bright",
        EmbeddedThemeName::MonokaiExtendedLight => "monokai-extended-light",
        EmbeddedThemeName::MonokaiExtendedOrigin => "monokai-extended-origin",
        EmbeddedThemeName::Nord => "nord",
        EmbeddedThemeName::OneHalfDark => "one-half-dark",
        EmbeddedThemeName::OneHalfLight => "one-half-light",
        EmbeddedThemeName::SolarizedDark => "solarized-dark",
        EmbeddedThemeName::SolarizedLight => "solarized-light",
        EmbeddedThemeName::SublimeSnazzy => "sublime-snazzy",
        EmbeddedThemeName::TwoDark => "two-dark",
        EmbeddedThemeName::Zenburn => "zenburn",
    }
}

fn probe_style(style: Style) -> ProbeStyle {
    ProbeStyle {
        r: style.foreground.r,
        g: style.foreground.g,
        b: style.foreground.b,
        a: style.foreground.a,
        bold: style.font_style.contains(FontStyle::BOLD),
    }
}

fn main() {
    let syntax_set = two_face::syntax::extra_newlines();
    let syntax = syntax_set.find_syntax_by_name("Rust").expect("Rust syntax");
    let themes = theme::extra();
    let mut output = Vec::new();
    for theme_name in EmbeddedLazyThemeSet::theme_names() {
        let theme = themes.get(*theme_name);
        let mut highlighter = HighlightLines::new(syntax, theme);
        let mut lines = Vec::new();
        for line in LinesWithEndings::from(CORPUS) {
            let spans = highlighter
                .highlight_line(line, &syntax_set)
                .expect("highlight role corpus")
                .into_iter()
                .filter_map(|(style, text)| {
                    let text = text.trim_end_matches(['\n', '\r']);
                    (!text.is_empty()).then(|| ProbeSpan {
                        text: text.to_string(),
                        style: probe_style(style),
                    })
                })
                .collect();
            lines.push(spans);
        }
        output.push(ThemeProbe {
            name: canonical_name(*theme_name),
            inserted_background: scope_background(theme, "markup.inserted", "diff.inserted"),
            deleted_background: scope_background(theme, "markup.deleted", "diff.deleted"),
            lines,
        });
    }
    println!("{}", serde_json::to_string(&output).expect("serialize probe"));
}
