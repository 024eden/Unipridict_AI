const {
  Document, Packer, Paragraph, TextRun, Table, TableRow, TableCell,
  AlignmentType, LevelFormat, HeadingLevel, BorderStyle, WidthType,
  ShadingType, PageBreak, PageNumber, NumberFormat, Header, Footer,
  TabStopType, TabStopPosition, VerticalAlign
} = require('docx');
const fs = require('fs');

// ─── Color palette ───────────────────────────────────────────────────────────
const DARK_BLUE   = "1A3C5E";
const MID_BLUE    = "2E6DA4";
const LIGHT_BLUE  = "D6E8F7";
const ACCENT      = "C0392B";
const GRAY_BG     = "F2F2F2";
const TEXT        = "1C1C1C";
const WHITE       = "FFFFFF";

// ─── Page margins (A4, 1.25" left for binding, 1" others) ────────────────────
const MARGINS = { top: 1440, right: 1440, bottom: 1440, left: 1800 };
const CONTENT_W = 11906 - 1440 - 1800; // A4 width minus margins

// ─── Reusable border preset ───────────────────────────────────────────────────
const THIN = { style: BorderStyle.SINGLE, size: 1, color: "CCCCCC" };
const cellBorders = { top: THIN, bottom: THIN, left: THIN, right: THIN };

// ─── Helper: blank paragraph ──────────────────────────────────────────────────
const blank = (sz = 6) => new Paragraph({ children: [new TextRun({ text: "", size: sz })] });

// ─── Helper: centered heading for front matter ────────────────────────────────
const centeredBold = (text, size = 28, color = DARK_BLUE) =>
  new Paragraph({
    alignment: AlignmentType.CENTER,
    spacing: { before: 160, after: 160 },
    children: [new TextRun({ text, bold: true, size, color, font: "Times New Roman" })]
  });

// ─── Helper: body paragraph ──────────────────────────────────────────────────
const body = (text, indent = false) =>
  new Paragraph({
    indent: indent ? { firstLine: 720 } : undefined,
    spacing: { before: 120, after: 120, line: 360 }, // double spacing ≈ 360
    children: [new TextRun({ text, size: 28, font: "Times New Roman", color: TEXT })]
  });

// ─── Helper: section label (e.g., "1.1 Background") ─────────────────────────
const subHead = (text, level = 2) => {
  const sizes = { 1: 32, 2: 28, 3: 26 };
  const colors = { 1: DARK_BLUE, 2: MID_BLUE, 3: TEXT };
  return new Paragraph({
    heading: level === 1 ? HeadingLevel.HEADING_1 : level === 2 ? HeadingLevel.HEADING_2 : HeadingLevel.HEADING_3,
    spacing: { before: 280, after: 140 },
    children: [new TextRun({ text, bold: true, size: sizes[level] || 26, color: colors[level] || TEXT, font: "Times New Roman" })]
  });
};

// ─── Helper: bullet item ─────────────────────────────────────────────────────
const bullet = (text) =>
  new Paragraph({
    numbering: { reference: "bullets", level: 0 },
    spacing: { before: 80, after: 80, line: 320 },
    children: [new TextRun({ text, size: 26, font: "Times New Roman", color: TEXT })]
  });

// ─── Helper: numbered item ───────────────────────────────────────────────────
const numbered = (text) =>
  new Paragraph({
    numbering: { reference: "numbers", level: 0 },
    spacing: { before: 80, after: 80, line: 320 },
    children: [new TextRun({ text, size: 26, font: "Times New Roman", color: TEXT })]
  });

// ─── Helper: divider rule under a heading ────────────────────────────────────
const rule = () =>
  new Paragraph({
    border: { bottom: { style: BorderStyle.SINGLE, size: 8, color: MID_BLUE, space: 1 } },
    spacing: { before: 0, after: 180 },
    children: [new TextRun("")]
  });

// ─── Helper: colored callout box ─────────────────────────────────────────────
const calloutBox = (label, text) =>
  new Table({
    width: { size: CONTENT_W, type: WidthType.DXA },
    columnWidths: [CONTENT_W],
    rows: [
      new TableRow({
        children: [new TableCell({
          borders: { top: { style: BorderStyle.SINGLE, size: 8, color: MID_BLUE }, bottom: THIN, left: { style: BorderStyle.SINGLE, size: 16, color: ACCENT }, right: THIN },
          shading: { fill: LIGHT_BLUE, type: ShadingType.CLEAR },
          margins: { top: 120, bottom: 120, left: 200, right: 200 },
          width: { size: CONTENT_W, type: WidthType.DXA },
          children: [
            new Paragraph({ spacing: { before: 60, after: 60 }, children: [new TextRun({ text: label, bold: true, size: 24, color: DARK_BLUE, font: "Times New Roman" })] }),
            new Paragraph({ spacing: { before: 40, after: 40 }, children: [new TextRun({ text, size: 24, font: "Times New Roman", color: TEXT })] })
          ]
        })]
      })
    ]
  });

// ─── Helper: two-column info table ───────────────────────────────────────────
const infoTable = (rows) => {
  const colW = Math.floor(CONTENT_W / 2);
  return new Table({
    width: { size: CONTENT_W, type: WidthType.DXA },
    columnWidths: [colW, colW],
    rows: rows.map(([k, v]) =>
      new TableRow({
        children: [
          new TableCell({
            borders: cellBorders, shading: { fill: GRAY_BG, type: ShadingType.CLEAR },
            width: { size: colW, type: WidthType.DXA },
            margins: { top: 80, bottom: 80, left: 160, right: 80 },
            children: [new Paragraph({ children: [new TextRun({ text: k, bold: true, size: 24, font: "Times New Roman", color: DARK_BLUE })] })]
          }),
          new TableCell({
            borders: cellBorders,
            width: { size: colW, type: WidthType.DXA },
            margins: { top: 80, bottom: 80, left: 160, right: 80 },
            children: [new Paragraph({ children: [new TextRun({ text: v, size: 24, font: "Times New Roman", color: TEXT })] })]
          })
        ]
      })
    )
  });
};

// ─── Helper: chapter title banner ────────────────────────────────────────────
const chapterBanner = (num, title) =>
  new Table({
    width: { size: CONTENT_W, type: WidthType.DXA },
    columnWidths: [CONTENT_W],
    rows: [
      new TableRow({
        children: [new TableCell({
          borders: { top: THIN, bottom: THIN, left: THIN, right: THIN },
          shading: { fill: DARK_BLUE, type: ShadingType.CLEAR },
          margins: { top: 200, bottom: 200, left: 300, right: 300 },
          width: { size: CONTENT_W, type: WidthType.DXA },
          children: [
            new Paragraph({
              alignment: AlignmentType.CENTER,
              children: [new TextRun({ text: `CHAPTER ${num}`, bold: true, size: 24, color: WHITE, font: "Times New Roman" })]
            }),
            new Paragraph({
              alignment: AlignmentType.CENTER,
              children: [new TextRun({ text: title, bold: true, size: 32, color: WHITE, font: "Times New Roman" })]
            })
          ]
        })]
      })
    ]
  });

// ─── Helper: page break ──────────────────────────────────────────────────────
const pageBreak = () => new Paragraph({ children: [new PageBreak()] });

// ═════════════════════════════════════════════════════════════════════════════
//  DOCUMENT ASSEMBLY
// ═════════════════════════════════════════════════════════════════════════════
const doc = new Document({
  numbering: {
    config: [
      {
        reference: "bullets",
        levels: [{ level: 0, format: LevelFormat.BULLET, text: "\u2022", alignment: AlignmentType.LEFT,
          style: { paragraph: { indent: { left: 720, hanging: 360 } } } }]
      },
      {
        reference: "numbers",
        levels: [{ level: 0, format: LevelFormat.DECIMAL, text: "%1.", alignment: AlignmentType.LEFT,
          style: { paragraph: { indent: { left: 720, hanging: 360 } } } }]
      }
    ]
  },
  styles: {
    default: { document: { run: { font: "Times New Roman", size: 28, color: TEXT } } },
    paragraphStyles: [
      { id: "Heading1", name: "Heading 1", basedOn: "Normal", next: "Normal", quickFormat: true,
        run: { size: 36, bold: true, color: DARK_BLUE, font: "Times New Roman" },
        paragraph: { spacing: { before: 360, after: 200 }, outlineLevel: 0 } },
      { id: "Heading2", name: "Heading 2", basedOn: "Normal", next: "Normal", quickFormat: true,
        run: { size: 30, bold: true, color: MID_BLUE, font: "Times New Roman" },
        paragraph: { spacing: { before: 240, after: 140 }, outlineLevel: 1 } },
      { id: "Heading3", name: "Heading 3", basedOn: "Normal", next: "Normal", quickFormat: true,
        run: { size: 27, bold: true, color: TEXT, font: "Times New Roman" },
        paragraph: { spacing: { before: 180, after: 100 }, outlineLevel: 2 } }
    ]
  },
  sections: [{
    properties: {
      page: {
        size: { width: 11906, height: 16838 }, // A4
        margin: MARGINS
      }
    },
    headers: {
      default: new Header({
        children: [
          new Paragraph({
            border: { bottom: { style: BorderStyle.SINGLE, size: 6, color: MID_BLUE, space: 1 } },
            spacing: { after: 120 },
            children: [
              new TextRun({ text: "AFFORDABLE HIGH-DENSITY HOUSING FOR RAPIDLY URBANIZING CITIES", size: 18, color: MID_BLUE, font: "Times New Roman" }),
              new TextRun({ children: [new PageNumber()], size: 18, color: GRAY_BG }) // hidden page num in header
            ]
          })
        ]
      })
    },
    footers: {
      default: new Footer({
        children: [
          new Paragraph({
            border: { top: { style: BorderStyle.SINGLE, size: 6, color: MID_BLUE, space: 1 } },
            spacing: { before: 120 },
            tabStops: [{ type: TabStopType.RIGHT, position: CONTENT_W }],
            children: [
              new TextRun({ text: "B.Arch Final Year Project Report | Anna University", size: 18, color: MID_BLUE, font: "Times New Roman" }),
              new TextRun({ text: "\t", size: 18 }),
              new TextRun({ children: [new PageNumber()], size: 18, bold: true, color: DARK_BLUE })
            ]
          })
        ]
      })
    },
    children: [

      // ══════════════════════════════════════════════════════════════════════
      // COVER PAGE
      // ══════════════════════════════════════════════════════════════════════
      blank(240),
      centeredBold("ANNA UNIVERSITY :: CHENNAI 600 025", 22, MID_BLUE),
      blank(60),
      centeredBold("AFFORDABLE HIGH-DENSITY HOUSING FOR RAPIDLY URBANIZING CITIES", 36, DARK_BLUE),
      blank(120),
      new Paragraph({ alignment: AlignmentType.CENTER, spacing: { before: 80, after: 80 }, children: [new TextRun({ text: "A PROJECT REPORT", size: 28, font: "Times New Roman" })] }),
      blank(40),
      new Paragraph({ alignment: AlignmentType.CENTER, spacing: { before: 60, after: 60 }, children: [new TextRun({ text: "Submitted by", size: 26, italics: true, font: "Times New Roman" })] }),
      centeredBold("[YOUR FULL NAME]", 30),
      new Paragraph({ alignment: AlignmentType.CENTER, spacing: { before: 60, after: 60 }, children: [new TextRun({ text: "[REGISTER NUMBER]", size: 26, font: "Times New Roman" })] }),
      blank(80),
      new Paragraph({ alignment: AlignmentType.CENTER, spacing: { before: 60, after: 60 }, children: [new TextRun({ text: "in partial fulfillment for the award of the degree of", size: 26, italics: true, font: "Times New Roman" })] }),
      centeredBold("BACHELOR OF ARCHITECTURE", 30, DARK_BLUE),
      blank(80),
      new Paragraph({ alignment: AlignmentType.CENTER, spacing: { before: 60, after: 60 }, children: [new TextRun({ text: "in", size: 26, italics: true, font: "Times New Roman" })] }),
      centeredBold("ARCHITECTURE", 30, DARK_BLUE),
      blank(120),
      centeredBold("[NAME OF YOUR INSTITUTION]", 28, TEXT),
      centeredBold("ANNA UNIVERSITY :: CHENNAI 600 025", 26, MID_BLUE),
      blank(120),
      centeredBold("MAY 2025", 28, DARK_BLUE),

      pageBreak(),

      // ══════════════════════════════════════════════════════════════════════
      // BONAFIDE CERTIFICATE
      // ══════════════════════════════════════════════════════════════════════
      centeredBold("ANNA UNIVERSITY :: CHENNAI 600 025", 22, MID_BLUE),
      blank(40),
      centeredBold("BONAFIDE CERTIFICATE", 32, DARK_BLUE),
      rule(),
      blank(60),
      body('Certified that this project report "AFFORDABLE HIGH-DENSITY HOUSING FOR RAPIDLY URBANIZING CITIES" is the bonafide work of "[YOUR FULL NAME]" who carried out the project work under my supervision.', true),
      blank(200),
      infoTable([
        ["SIGNATURE", "SIGNATURE"],
        ["Head of Department", "Supervisor"],
        ["[Name of HOD]", "[Supervisor's Name]"],
        ["HEAD OF THE DEPARTMENT", "SUPERVISOR"],
        ["Department of Architecture", "Department of Architecture"],
        ["[Full College Address]", "[Full College Address]"]
      ]),

      pageBreak(),

      // ══════════════════════════════════════════════════════════════════════
      // ABSTRACT
      // ══════════════════════════════════════════════════════════════════════
      centeredBold("ABSTRACT", 32, DARK_BLUE),
      rule(),
      blank(40),
      body("This dissertation explores affordable high-density housing as a critical architectural and urban response to rapid urbanization in developing cities. With the global urban population projected to reach 6.7 billion by 2050, the demand for accessible, dignified, and sustainable urban housing has never been more urgent. Indian cities, in particular, face acute challenges: informal settlements house over 65 million people, urban land costs have become prohibitive, and infrastructure strain is mounting.", true),
      blank(30),
      body("This research investigates the intersection of urban density, affordability, and architectural quality through a multi-layered methodology combining theoretical frameworks, case study analysis, policy evaluation, and an original design proposal. The study critically examines landmark housing precedents — including B.V. Doshi's Aranya Township in Indore, Singapore's public housing estates, Elemental's incremental housing in Chile, and the proposed Dharavi Redevelopment — to extract transferable design principles.", true),
      blank(30),
      body("Key findings suggest that affordability is not achieved through cost-cutting alone, but through intelligent planning strategies: mixed-use vertical typologies, modular incremental construction, community-centric spatial planning, and integration with transit infrastructure. The research also reveals that successful high-density housing must balance density with liveability — ensuring access to natural light, ventilation, green open spaces, and community amenities.", true),
      blank(30),
      body("The study concludes with an original architectural design proposal for a mixed-income, high-density housing cluster in a rapidly urbanizing Indian city context, incorporating G+8 residential blocks, shared green courtyards, active ground-floor commercial uses, and passive climate-responsive strategies. The proposed model demonstrates that affordability, density, and architectural quality are not mutually exclusive — they can and must coexist.", true),
      blank(30),
      calloutBox("Keywords:", "Affordable Housing, High-Density Urban Housing, Urbanization, Housing Policy, Mixed-Income Communities, Incremental Housing, Sustainable Design, Urban Regeneration, India."),

      pageBreak(),

      // ══════════════════════════════════════════════════════════════════════
      // TABLE OF CONTENTS
      // ══════════════════════════════════════════════════════════════════════
      centeredBold("TABLE OF CONTENTS", 32, DARK_BLUE),
      rule(),
      blank(40),
      ...([
        ["ABSTRACT", "iii"],
        ["LIST OF TABLES", "v"],
        ["LIST OF FIGURES", "vi"],
        ["LIST OF ABBREVIATIONS", "viii"],
        ["CHAPTER 1 — INTRODUCTION", "1"],
        ["    1.1 Background and Context", "2"],
        ["    1.2 Problem Statement", "4"],
        ["    1.3 Aims and Objectives", "5"],
        ["    1.4 Scope and Limitations", "6"],
        ["    1.5 Research Methodology", "7"],
        ["CHAPTER 2 — LITERATURE REVIEW", "9"],
        ["    2.1 Defining Density and Affordability", "10"],
        ["    2.2 Global Urbanization Trends", "12"],
        ["    2.3 Housing Typologies in Urban Contexts", "15"],
        ["    2.4 Socio-Cultural Dimensions of Housing", "18"],
        ["    2.5 Summary of Key Findings", "21"],
        ["CHAPTER 3 — PRINCIPLES OF AFFORDABLE HIGH-DENSITY HOUSING", "23"],
        ["    3.1 Land Use Efficiency", "24"],
        ["    3.2 Economic Viability", "26"],
        ["    3.3 Social Equity and Inclusivity", "28"],
        ["    3.4 Environmental Sustainability", "30"],
        ["    3.5 Liveability and Urban Quality", "32"],
        ["CHAPTER 4 — DESIGN STRATEGIES", "35"],
        ["    4.1 Vertical Housing Typologies", "36"],
        ["    4.2 Modular and Incremental Construction", "39"],
        ["    4.3 Mixed-Use Ground Floor Activation", "42"],
        ["    4.4 Community Spaces and Open Areas", "44"],
        ["    4.5 Passive Climate Design", "46"],
        ["CHAPTER 5 — CASE STUDIES", "50"],
        ["    5.1 Aranya Township, Indore — B.V. Doshi", "51"],
        ["    5.2 HDB Public Housing, Singapore", "55"],
        ["    5.3 Quinta Monroy, Chile — Elemental", "59"],
        ["    5.4 Dharavi Redevelopment Project, Mumbai", "63"],
        ["    5.5 Comparative Analysis", "67"],
        ["CHAPTER 6 — POLICIES AND GOVERNANCE", "70"],
        ["    6.1 Pradhan Mantri Awas Yojana (PMAY)", "71"],
        ["    6.2 Urban Land Ceiling and Regulation Acts", "74"],
        ["    6.3 FSI and Zoning Regulations", "76"],
        ["    6.4 International Policy Models", "79"],
        ["    6.5 Policy Gaps and Recommendations", "82"],
        ["CHAPTER 7 — CHALLENGES AND BARRIERS", "85"],
        ["    7.1 Financial and Economic Constraints", "86"],
        ["    7.2 Infrastructure and Service Delivery", "88"],
        ["    7.3 Social Resistance and Community Issues", "90"],
        ["    7.4 Land Acquisition Challenges", "92"],
        ["    7.5 Environmental and Structural Concerns", "94"],
        ["CHAPTER 8 — DESIGN PROPOSAL", "97"],
        ["    8.1 Site Selection and Analysis", "98"],
        ["    8.2 Design Concept and Philosophy", "102"],
        ["    8.3 Master Plan and Spatial Organization", "105"],
        ["    8.4 Architectural Program and Unit Mix", "109"],
        ["    8.5 Construction and Material Strategy", "113"],
        ["    8.6 Sustainability Features", "116"],
        ["CHAPTER 9 — CONCLUSION", "119"],
        ["    9.1 Summary of Key Findings", "120"],
        ["    9.2 Contributions to the Discipline", "122"],
        ["    9.3 Future Research Directions", "123"],
        ["APPENDICES", "125"],
        ["REFERENCES", "130"]
      ].map(([item, pg]) =>
        new Paragraph({
          tabStops: [{ type: TabStopType.RIGHT, position: CONTENT_W, leader: TabStopType.DOT }],
          spacing: { before: 80, after: 80, line: 280 },
          children: [
            new TextRun({ text: item, size: item.startsWith("CHAPTER") || item === "ABSTRACT" || item === "LIST" || item === "APPENDICES" || item === "REFERENCES" ? 26 : 24, bold: item.startsWith("CHAPTER"), color: item.startsWith("CHAPTER") ? DARK_BLUE : TEXT, font: "Times New Roman" }),
            new TextRun({ text: "\t" + pg, size: 24, font: "Times New Roman", color: TEXT })
          ]
        })
      )),

      pageBreak(),

      // ══════════════════════════════════════════════════════════════════════
      // LIST OF TABLES
      // ══════════════════════════════════════════════════════════════════════
      centeredBold("LIST OF TABLES", 32, DARK_BLUE),
      rule(),
      blank(30),
      ...[
        ["Table 1.1", "Research Methodology Matrix", "8"],
        ["Table 2.1", "Global Urban Population Growth Projections", "13"],
        ["Table 2.2", "Comparative Housing Density Standards across Countries", "16"],
        ["Table 3.1", "Land Use Efficiency Benchmarks", "25"],
        ["Table 3.2", "Cost Breakdown of Affordable Housing per Square Metre", "27"],
        ["Table 4.1", "Comparison of Housing Typologies — Strengths and Trade-offs", "38"],
        ["Table 4.2", "Passive Design Strategy Checklist", "48"],
        ["Table 5.1", "Case Study Comparison Matrix", "67"],
        ["Table 6.1", "PMAY Scheme Benefits and Eligibility Criteria", "73"],
        ["Table 6.2", "FSI Regulations Across Major Indian Cities", "77"],
        ["Table 8.1", "Site Analysis Summary", "101"],
        ["Table 8.2", "Architectural Programme — Area Schedule", "111"],
        ["Table 8.3", "Unit Mix and Cost Estimate", "112"]
      ].map(([num, caption, pg]) =>
        new Paragraph({
          tabStops: [{ type: TabStopType.RIGHT, position: CONTENT_W }],
          spacing: { before: 80, after: 80 },
          children: [
            new TextRun({ text: `${num}  ${caption}`, size: 24, font: "Times New Roman", color: TEXT }),
            new TextRun({ text: "\t" + pg, size: 24, font: "Times New Roman", color: MID_BLUE, bold: true })
          ]
        })
      ),

      pageBreak(),

      // ══════════════════════════════════════════════════════════════════════
      // LIST OF FIGURES
      // ══════════════════════════════════════════════════════════════════════
      centeredBold("LIST OF FIGURES", 32, DARK_BLUE),
      rule(),
      blank(30),
      ...[
        ["Fig 1.1", "World Urban Population Growth Chart (UN 2023)", "3"],
        ["Fig 1.2", "Research Methodology Flowchart", "8"],
        ["Fig 2.1", "Informal Settlement Distribution Map — Indian Cities", "11"],
        ["Fig 2.2", "Density Spectrum — Low to High Rise Typologies", "15"],
        ["Fig 3.1", "Principles Framework Diagram", "23"],
        ["Fig 3.2", "Mixed-Use Zoning Schematic", "29"],
        ["Fig 4.1", "Vertical Housing Typology Examples", "37"],
        ["Fig 4.2", "Modular Unit Assembly Diagram", "40"],
        ["Fig 4.3", "Street-Level Activation Concept Sketch", "43"],
        ["Fig 4.4", "Wind Flow and Passive Ventilation Strategy", "47"],
        ["Fig 5.1", "Aranya Township Plan — Indore", "52"],
        ["Fig 5.2", "Aranya Housing Photographs", "54"],
        ["Fig 5.3", "HDB Singapore Block Typology", "56"],
        ["Fig 5.4", "Quinta Monroy Half-House Concept", "60"],
        ["Fig 5.5", "Dharavi Site Context Map", "64"],
        ["Fig 6.1", "PMAY Implementation Status Map", "72"],
        ["Fig 8.1", "Site Location Map", "99"],
        ["Fig 8.2", "Site Analysis Diagrams", "100"],
        ["Fig 8.3", "Conceptual Master Plan", "105"],
        ["Fig 8.4", "Block Arrangement Diagram", "107"],
        ["Fig 8.5", "Typical Floor Plan — 1BHK and 2BHK Units", "110"],
        ["Fig 8.6", "Sections and Elevations", "114"],
        ["Fig 8.7", "Perspective Renders", "117"],
        ["Fig 8.8", "Sustainability Strategy Diagram", "116"]
      ].map(([num, caption, pg]) =>
        new Paragraph({
          tabStops: [{ type: TabStopType.RIGHT, position: CONTENT_W }],
          spacing: { before: 80, after: 80 },
          children: [
            new TextRun({ text: `${num}  ${caption}`, size: 24, font: "Times New Roman", color: TEXT }),
            new TextRun({ text: "\t" + pg, size: 24, font: "Times New Roman", color: MID_BLUE, bold: true })
          ]
        })
      ),

      pageBreak(),

      // ══════════════════════════════════════════════════════════════════════
      // LIST OF ABBREVIATIONS
      // ══════════════════════════════════════════════════════════════════════
      centeredBold("LIST OF SYMBOLS, ABBREVIATIONS AND NOMENCLATURE", 28, DARK_BLUE),
      rule(),
      blank(30),
      infoTable([
        ["BHK", "Bedroom, Hall, Kitchen"],
        ["EWS", "Economically Weaker Section"],
        ["FAR / FSI", "Floor Area Ratio / Floor Space Index"],
        ["GDP", "Gross Domestic Product"],
        ["GFA", "Gross Floor Area"],
        ["HIG", "Higher Income Group"],
        ["HDB", "Housing Development Board (Singapore)"],
        ["LIG", "Lower Income Group"],
        ["MIG", "Middle Income Group"],
        ["MLA", "Maximum Liveable Area"],
        ["PMAY", "Pradhan Mantri Awas Yojana"],
        ["PPP", "Public Private Partnership"],
        ["SDG", "Sustainable Development Goal"],
        ["TERI", "The Energy and Resources Institute"],
        ["TDR", "Transferable Development Rights"],
        ["TOD", "Transit Oriented Development"],
        ["UN", "United Nations"],
        ["UNFPA", "United Nations Population Fund"],
        ["UDPFI", "Urban Development Plans Formulation & Implementation"]
      ]),

      pageBreak(),

      // ══════════════════════════════════════════════════════════════════════
      // CHAPTER 1 — INTRODUCTION
      // ══════════════════════════════════════════════════════════════════════
      chapterBanner("1", "INTRODUCTION"),
      blank(60),
      subHead("1.1 Background and Context", 2),
      body("Urbanization is one of the most powerful and transformative forces shaping our world. By 2050, approximately 68% of the global population — nearly 6.7 billion people — will live in urban areas, with the vast majority of this growth occurring in the developing regions of Asia and Sub-Saharan Africa. This unprecedented demographic shift is producing a crisis of urban housing affordability and accessibility, most acutely felt in cities of the Global South.", true),
      blank(20),
      body("India exemplifies this challenge with particular urgency. With over 35% of its population already urbanized and projections indicating a further doubling by 2050, Indian cities must provide housing for an additional 400 million urban dwellers over the next three decades. The urban housing shortage in India currently stands at approximately 18.78 million units, with over 95% of this deficit concentrated among Economically Weaker Sections (EWS) and Lower Income Groups (LIG). Simultaneously, rapid land price escalation, speculative real estate markets, and inadequate infrastructure have pushed low-income households to peripheral, poorly serviced informal settlements.", true),
      blank(20),
      calloutBox("Global Context:", "The United Nations Sustainable Development Goal 11 calls for making cities inclusive, safe, resilient, and sustainable by 2030, with specific targets around ensuring access to adequate, safe, and affordable housing for all. Achieving this requires a fundamental rethinking of urban housing — not merely as a building problem, but as a complex architectural, social, economic, and political challenge."),
      blank(40),
      subHead("1.2 Problem Statement", 2),
      body("The central problem this dissertation addresses is: How can architectural design and urban planning principles generate affordable, liveable, and high-density housing solutions that are responsive to the socio-economic, cultural, and environmental context of rapidly urbanizing Indian cities?", true),
      blank(20),
      body("The conventional housing provision models in India have largely failed to address this challenge: market-led development prioritizes profitable high-end housing, government schemes suffer from implementation gaps, and informal self-built settlements — while demonstrating remarkable community ingenuity — lack structural safety, services, and security of tenure.", true),
      blank(40),
      subHead("1.3 Aims and Objectives", 2),
      body("The primary aim of this dissertation is to develop a comprehensive architectural framework for affordable high-density housing in rapidly urbanizing cities, informed by rigorous analysis of precedents, principles, and policies.", true),
      blank(20),
      body("The specific objectives are:"),
      bullet("To critically review existing literature on urban density, housing affordability, and sustainable housing design."),
      bullet("To identify core principles that define successful affordable high-density housing."),
      bullet("To analyze and extract lessons from landmark housing case studies globally and in India."),
      bullet("To evaluate the policy landscape governing affordable housing in India."),
      bullet("To identify key barriers and challenges in the delivery of such housing."),
      bullet("To synthesize findings into an original architectural design proposal."),
      blank(40),
      subHead("1.4 Scope and Limitations", 2),
      body("This study focuses primarily on the Indian urban housing context, with comparative references to international precedents. The research encompasses housing for EWS, LIG, and MIG groups in rapidly growing tier-1 and tier-2 cities. The design proposal is developed at the architectural scale with indicative structural and services strategies.", true),
      blank(20),
      body("Limitations include the absence of primary site-specific structural engineering analysis, the rapidly evolving policy landscape which may not reflect latest government revisions, and the inherently generalizing nature of a dissertation compared to site-specific professional practice."),
      blank(40),
      subHead("1.5 Research Methodology", 2),
      body("This dissertation employs a qualitative, multi-method research approach, combining:"),
      bullet("Secondary Literature Review — academic journals, planning reports, UN and World Bank publications."),
      bullet("Precedent Studies — in-depth architectural and urban analysis of selected housing projects."),
      bullet("Policy Analysis — review of national and state-level housing policies."),
      bullet("Design Research — synthesis of findings into an original architectural proposal."),
      blank(20),
      calloutBox("Methodology Note:", "All case study analysis is based on published documentation, architectural drawings, and site reports. Primary field surveys were not conducted due to logistical constraints. The design proposal is developed at concept design stage (1:500 to 1:200 scale)."),

      pageBreak(),

      // ══════════════════════════════════════════════════════════════════════
      // CHAPTER 2 — LITERATURE REVIEW
      // ══════════════════════════════════════════════════════════════════════
      chapterBanner("2", "LITERATURE REVIEW"),
      blank(60),
      subHead("2.1 Defining Density and Affordability", 2),
      body("The concept of 'density' in urban housing is more nuanced than its common perception suggests. Jacobs (1961), in 'The Death and Life of Great American Cities', argued that density is not merely a quantitative measure but a qualitative urban condition — one that enables the social interactions, economic activity, and diversity that make cities vital. Density can be measured as dwelling units per hectare (DPH), population per hectare, or Floor Area Ratio (FAR/FSI).", true),
      blank(20),
      body("Affordability, by contrast, is typically defined economically: housing is considered affordable when a household spends no more than 30% of its gross income on housing costs. The Reserve Bank of India's Housing Affordability Index, and the National Housing Bank's housing data, consistently reveal that this threshold is breached for over 60% of urban Indian households in major cities.", true),
      blank(20),
      calloutBox("Key Theorists to Cite:", "Jane Jacobs (1961), Christopher Alexander (A Pattern Language, 1977), Charles Correa (New Landscape, 1985), B.V. Doshi (Aranya, 1989), Peter Hall (Cities of Tomorrow, 1988), UN-Habitat (various reports), Alejandro Aravena (Elemental, 2016)."),
      blank(40),
      subHead("2.2 Global Urbanization Trends", 2),
      body("According to UN-Habitat's World Cities Report (2022), the world's urban population will increase by 2.5 billion by 2050, with 90% of this growth concentrated in Asia and Africa. Megacities (populations over 10 million) are multiplying, but the most significant growth is occurring in medium-sized cities of 500,000 to 5 million — cities with the least institutional capacity to respond.", true),
      blank(20),
      body("India's urban growth is particularly dramatic: cities like Surat, Pune, Hyderabad, and Vijayawada are among the world's fastest-growing urban centres. The National Sample Survey Organization (NSSO) reports that rural-to-urban migration continues at historically high rates, driven by agricultural distress, rural unemployment, and urban economic opportunity.", true),
      blank(40),
      subHead("2.3 Housing Typologies in Urban Contexts", 2),
      body("Literature on housing typologies distinguishes between several broad categories relevant to affordable high-density contexts:"),
      blank(10),
      body("Low-Rise High-Density (LRHD): Typologies of 2-4 storeys achieving 150-250 DPH through tight street grids and small lots. Successful in cities like Amsterdam and Barcelona. Challenged by land economics in high-cost Indian urban land markets.", true),
      blank(10),
      body("Mid-Rise (5-12 storeys): The most commonly recommended affordable high-density typology, capable of achieving 300-500 DPH with reasonable construction costs, elevator requirements, and manageable social dynamics.", true),
      blank(10),
      body("High-Rise (12+ storeys): Achieved in Singapore's HDB estates at 800+ DPH, requiring sophisticated management systems, high capital costs, and strong institutional support. Less transferable to weaker institutional contexts.", true),
      blank(40),
      subHead("2.4 Socio-Cultural Dimensions of Housing", 2),
      body("A recurrent theme in housing literature is the failure of top-down mass housing to account for the social and cultural dimensions of dwelling. Rapoport (1969) in 'House Form and Culture' established that housing is not merely shelter but a complex social institution that embodies cultural values, family structures, and community practices.", true),
      blank(20),
      body("In the Indian context, the joint family system, the importance of semi-private transitional spaces (verandahs, chowks), street-level economic activity, and gender-specific spatial requirements significantly influence what constitutes 'adequate' housing. Mass housing schemes that ignore these factors — as many government housing projects historically have — tend to suffer from social rejection, abandonment, and subsequent informal modification.", true),
      blank(40),
      subHead("2.5 Summary and Research Gaps", 2),
      body("The literature reveals significant consensus on the principles of successful affordable housing (community participation, mixed-use integration, incremental provision) but significant gaps in: (a) India-specific design guidance for climate-responsive high-density housing; (b) post-occupancy evaluation of government housing schemes; and (c) integrated frameworks connecting architectural design with policy and financing. This dissertation addresses the last gap in particular."),

      pageBreak(),

      // ══════════════════════════════════════════════════════════════════════
      // CHAPTER 3 — PRINCIPLES
      // ══════════════════════════════════════════════════════════════════════
      chapterBanner("3", "PRINCIPLES OF AFFORDABLE HIGH-DENSITY HOUSING"),
      blank(60),
      body("Synthesizing the literature reviewed in Chapter 2 and the urban housing precedents studied, this chapter articulates the core principles that must guide the design of affordable high-density housing. These principles form the evaluative framework applied in the case study analysis (Chapter 5) and the design proposal (Chapter 8)."),
      blank(40),
      subHead("3.1 Efficient Land Use", 2),
      body("Land is the single most expensive input in urban housing delivery. Efficient land use means maximizing the number of affordable dwellings per unit of land without compromising liveability. This requires high FAR/FSI utilization, minimizing non-usable areas, and applying mixed-use development to generate commercial revenue that cross-subsidizes residential affordability.", true),
      blank(20),
      infoTable([
        ["Target Metric", "Benchmark Value"],
        ["Dwelling Units per Hectare", "300 – 600 DPH"],
        ["FSI Utilization", "> 2.5 (urban cores)"],
        ["Open Space per Dwelling", "Minimum 4 sq.m per unit"],
        ["Ground Coverage", "Maximum 40%"]
      ]),
      blank(40),
      subHead("3.2 Economic Viability and Affordability", 2),
      body("A housing scheme is economically viable only if it can be built, maintained, and occupied sustainably. Cross-subsidization strategies — where market-rate and affordable units share the same development — are increasingly effective. The Inclusionary Zoning model mandates that a proportion (typically 20-30%) of any large residential development be reserved for affordable units.", true),
      bullet("Construction cost targets for EWS housing: below Rs. 3,000-4,000 per sq.ft using cost-effective technologies."),
      bullet("Rental and installment structures affordable on urban minimum wage."),
      bullet("Life-cycle cost analysis must include maintenance, utilities, and community management."),
      blank(40),
      subHead("3.3 Social Equity and Inclusivity", 2),
      body("Affordable housing must actively work against spatial segregation and social exclusion. Mixed-income communities, where households of different economic levels coexist in the same residential cluster, have been shown to produce better socioeconomic outcomes for lower-income residents while reducing the stigmatization of affordable housing.", true),
      blank(20),
      body("Gender-responsive design is also critical: women's safety, accessibility for elderly and disabled residents, and adequate childcare and community spaces all constitute dimensions of housing equity that conventional provision often neglects."),
      blank(40),
      subHead("3.4 Environmental Sustainability", 2),
      body("Affordable housing developments must not compromise environmental sustainability. Compact urban forms inherently reduce per-capita energy consumption, infrastructure costs, and ecological footprint compared to sprawling low-density alternatives. However, affordable housing must additionally incorporate:"),
      bullet("Passive climate design: orientation, shading, cross-ventilation, daylighting."),
      bullet("Rainwater harvesting and greywater recycling systems."),
      bullet("Robust green infrastructure: trees, vegetated surfaces, ecological corridors."),
      bullet("Use of recycled and locally sourced materials to reduce embodied carbon."),
      blank(40),
      subHead("3.5 Liveability and Urban Quality", 2),
      body("Density without quality produces slums. Every affordable housing project must achieve the fundamental standards of liveability: adequate dwelling size, access to natural light and ventilation in every unit, noise privacy, thermal comfort, and access to shared amenities. Community spaces — courtyards, playgrounds, community halls — are not luxuries but essential infrastructure for social well-being."),
      blank(20),
      calloutBox("Liveability Benchmarks:", "Every habitable room must receive a minimum of 2 hours of direct sunlight per day. Every unit must have access to mechanical or natural cross-ventilation. No corridor should exceed 30 metres without access to natural light. Communal open space should be provided at a minimum of 4 sqm per dwelling unit."),

      pageBreak(),

      // ══════════════════════════════════════════════════════════════════════
      // CHAPTER 4 — DESIGN STRATEGIES
      // ══════════════════════════════════════════════════════════════════════
      chapterBanner("4", "DESIGN STRATEGIES"),
      blank(60),
      body("This chapter translates the broad principles articulated in Chapter 3 into specific architectural and urban design strategies. Each strategy is discussed in terms of its spatial implications, technical requirements, and applicability to the Indian context."),
      blank(40),
      subHead("4.1 Vertical Housing Typologies", 2),
      body("The selection of building typology — point block, slab block, courtyard block, or hybrid — profoundly determines the social, spatial, and environmental qualities of the housing development.", true),
      blank(20),
      body("Slab blocks (linear multi-storey blocks) allow efficient unit stacking with through-ventilation for all units, clear orientation control, and straightforward structural systems. However, very long slab blocks can create monolithic urban edges and poor activation at ground level."),
      blank(20),
      body("Courtyard blocks create shared protected outdoor spaces at the residential cluster scale, enabling community interaction and a climate-moderated outdoor space. This typology draws from the traditional Indian chowk and is particularly appropriate for the Indian cultural context."),
      blank(20),
      body("For the purposes of this dissertation, a hybrid typology is proposed: short slab blocks (maximum 60m length) arranged around shared courtyards, at heights of G+8 to G+12, achieving approximately 400-500 DPH while maintaining adequate daylight and courtyard quality."),
      blank(40),
      subHead("4.2 Modular and Incremental Housing", 2),
      body("The concept of incremental housing — pioneered theoretically by John F.C. Turner (Housing by People, 1976) and architecturally demonstrated by Alejandro Aravena's Elemental practice — proposes that housing affordability can be achieved by delivering a structural 'half-house' that can be incrementally completed by residents over time. This strategy reduces initial capital requirement, allows dwelling size to grow with family income, and builds on the evident capacity and motivation of residents to invest in their own dwellings.", true),
      blank(20),
      calloutBox("Elemental's Half-House Strategy:", "Elemental (Chile) provides the structurally complex 'hard half' — staircase, bathroom, kitchen — and leaves the simpler 'soft half' for resident completion. This approach has been replicated in over 2,500 units globally."),
      blank(40),
      subHead("4.3 Mixed-Use Ground Floor Activation", 2),
      body("Monotonous residential ground floors produce unsafe, inactive street edges. Mixed-use programming at the ground level — integrating small shops, markets, workshops, childcare centres, and community rooms — generates economic activity, passive surveillance, street vitality, and community social infrastructure.", true),
      blank(20),
      body("In the Indian urban context, the street economy is not incidental but central: it provides livelihoods for EWS and LIG households, reduces commute times, and supports the social life of the community. Housing design must formally accommodate this rather than suppress it."),
      blank(40),
      subHead("4.4 Community Spaces and Green Infrastructure", 2),
      body("Community spaces are the connective tissue of residential communities. Hierarchical open space provision — from the private dwelling balcony, to the shared staircase landing, to the courtyard, to the neighbourhood park — creates a graduated transition from private to public life that is fundamental to residential well-being.", true),
      bullet("Private balconies: minimum 4 sqm per unit."),
      bullet("Semi-private staircase landings: minimum 12 sqm per floor per core."),
      bullet("Shared courtyard: minimum 400 sqm per residential cluster."),
      bullet("Neighbourhood park: minimum 1,200 sqm per 500 units."),
      blank(40),
      subHead("4.5 Passive Climate Design for Indian Conditions", 2),
      body("India's diverse climate zones — hot-dry (Rajasthan), hot-humid (coastal), composite (Delhi), and temperate (north) — demand differentiated climate design responses. For the hot-humid context of most rapidly urbanizing South Indian cities:", true),
      bullet("Orientation: long axis on east-west axis, minimizing west-facing glazed areas."),
      bullet("Shading: deep overhangs (minimum 1.2m), vertical fins on east and west."),
      bullet("Ventilation: through-ventilation in all units, minimum 8% window-to-floor ratio."),
      bullet("Materials: high thermal mass at ground level, lightweight insulated roof."),
      bullet("Landscaping: trees and green roofs to reduce urban heat island effect."),

      pageBreak(),

      // ══════════════════════════════════════════════════════════════════════
      // CHAPTER 5 — CASE STUDIES
      // ══════════════════════════════════════════════════════════════════════
      chapterBanner("5", "CASE STUDIES"),
      blank(60),
      body("Case study analysis forms the empirical core of this dissertation. Four landmark projects are studied in depth, selected for their architectural significance, geographical relevance, and the transferability of their lessons to the Indian context."),
      blank(40),
      subHead("5.1 Aranya Township, Indore — B.V. Doshi (1989)", 2),
      body("The Aranya Housing Project, designed by B.V. Doshi for the Indore Development Authority, is arguably the most significant affordable housing project in Indian architectural history, and a project that earned Doshi the Pritzker Prize in 2018. The project provided serviced plots to 80,000 residents across income groups on a 86-hectare site, with an elaborate infrastructure of streets, drainage, water, and electricity to which residents could build incrementally.", true),
      blank(20),
      body("Architectural Contribution: Aranya demonstrated that the role of the architect in mass housing is not to design every dwelling but to create the spatial framework — the street hierarchy, the plot sizes, the shared infrastructure — within which communities can build their own housing over time. The result is genuine architectural diversity, community ownership, and social cohesion that no top-down scheme has replicated."),
      blank(20),
      infoTable([
        ["Location", "Indore, Madhya Pradesh, India"],
        ["Architect", "B.V. Doshi / Vastushilpa Foundation"],
        ["Year", "1989 (initial phase)"],
        ["Area", "86 Hectares"],
        ["Residents", "80,000+ (approx. 14,000 families)"],
        ["Strategy", "Serviced plots, incremental self-build"],
        ["Award", "Aga Khan Award for Architecture, 1995"]
      ]),
      blank(40),
      subHead("5.2 HDB Public Housing, Singapore", 2),
      body("Singapore's Housing Development Board (HDB) is widely recognized as the world's most successful public housing system. Established in 1960, it now houses over 80% of Singapore's resident population in high-rise, high-density estates that provide quality housing, amenities, and community infrastructure.", true),
      blank(20),
      body("Architectural Contribution: Singapore's HDB model demonstrates that high-density housing need not mean low quality. Estates are designed with generous green spaces, active void-deck ground floors (historically used for community functions, funerals, and children's play), and a strong sense of place identity. The model is sustained by strong institutional capacity, long-term government financing, and a compulsory savings scheme (CPF) that makes ownership accessible."),
      blank(20),
      body("Transferability to India: Singapore's institutional model is difficult to replicate directly. However, design lessons — particularly around void-deck activation, green corridor integration, and typological variety within high-density — are highly relevant."),
      blank(40),
      subHead("5.3 Quinta Monroy, Iquique, Chile — Elemental (2004)", 2),
      body("Elemental's Quinta Monroy project in Iquique, Chile, provided housing for 100 families on the same urban site they had been informally occupying, within a constrained government subsidy of USD 7,500 per family. Architect Alejandro Aravena's critical insight was that this budget could deliver either a small complete house or a medium-sized 'half-house' with room to expand.", true),
      blank(20),
      body("The project delivered the structurally complex half (two-storey structure with staircase, bathroom, kitchen) and left the other half for resident expansion. Within 3 years of occupation, residents had doubled the floor area of their dwellings, significantly increasing the value of the public investment."),
      blank(40),
      subHead("5.4 Dharavi Redevelopment Project, Mumbai", 2),
      body("Dharavi, popularly described as Asia's largest slum, houses approximately 700,000 residents in an extremely dense, organically evolved urban settlement of extraordinary social and economic complexity. The Dharavi Redevelopment Project (DRP) has been in various stages of planning since 2004, most recently with the Adani Group as the principal developer under a government-backed scheme.", true),
      blank(20),
      body("The project is studied here as a cautionary tale as much as a precedent. Its scale and complexity — relocating hundreds of thousands of residents while preserving their livelihoods and communities — exposes the limits of large-scale tabula rasa redevelopment. It also raises fundamental questions about the rights of informal settlement residents and the social justice dimensions of urban regeneration."),
      blank(40),
      subHead("5.5 Comparative Analysis", 2),
      body("The four case studies, when read together, reveal a spectrum of approaches to affordable high-density housing delivery:"),
      blank(20),
      infoTable([
        ["Project", "Aranya (India)"],
        ["Strategy", "Incremental / Plot-based"],
        ["Density", "Medium"],
        ["Community Agency", "Very High"],
        ["Replicability", "High in Indian context"]
      ]),
      blank(10),
      infoTable([
        ["Project", "HDB Singapore"],
        ["Strategy", "State-led mass provision"],
        ["Density", "Very High"],
        ["Community Agency", "Low to Medium"],
        ["Replicability", "Limited without strong institutions"]
      ]),
      blank(10),
      infoTable([
        ["Project", "Quinta Monroy"],
        ["Strategy", "Incremental half-house"],
        ["Density", "Medium-High"],
        ["Community Agency", "High"],
        ["Replicability", "High globally"]
      ]),

      pageBreak(),

      // ══════════════════════════════════════════════════════════════════════
      // CHAPTER 6 — POLICIES
      // ══════════════════════════════════════════════════════════════════════
      chapterBanner("6", "POLICIES AND GOVERNANCE"),
      blank(60),
      body("Architectural design for affordable housing does not occur in a policy vacuum. The financial viability, scale, and long-term success of affordable housing projects are profoundly shaped by the policy and regulatory environment. This chapter reviews the key policy instruments governing affordable housing in India and their implications for architectural practice."),
      blank(40),
      subHead("6.1 Pradhan Mantri Awas Yojana (PMAY)", 2),
      body("Launched in 2015 with the objective of 'Housing for All by 2022', Pradhan Mantri Awas Yojana (PMAY) is India's flagship affordable housing scheme. It operates across four verticals: In-situ Slum Rehabilitation (ISR), Credit Linked Subsidy Scheme (CLSS), Affordable Housing in Partnership (AHP), and Beneficiary-Led Construction (BLC).", true),
      blank(20),
      body("The scheme has sanctioned approximately 11.85 million dwelling units as of 2023, of which a significant number remain incomplete due to fund shortfalls, land acquisition delays, and implementation challenges. The central subsidy of Rs. 1.5 lakh per EWS beneficiary for BLC, while meaningful, is inadequate in high-cost urban land markets."),
      blank(40),
      subHead("6.2 FSI/FAR Regulations and Incentives", 2),
      body("Floor Space Index (FSI) or Floor Area Ratio (FAR) is the primary regulatory tool governing the density of urban development. In most major Indian cities, base FSI is restricted to 1.5-2.5, significantly below the 4.0-8.0+ FSI commonly used in Singapore and Hong Kong for comparable density targets.", true),
      blank(20),
      body("Relaxed or premium FSI for affordable housing projects — as adopted in Maharashtra (FSI 4.0 for slum rehabilitation), Tamil Nadu, and Gujarat — provides a powerful incentive for private sector participation. However, higher FSI without complementary investment in infrastructure (roads, water, sewage, power) produces overcrowded, poorly serviced developments."),
      blank(40),
      subHead("6.3 Transit-Oriented Development (TOD) Policy", 2),
      body("The National Transit-Oriented Development Policy (MoHUA, 2017) designates a high-density, mixed-use development zone within 500-800m of metro and bus rapid transit stations. TOD policy allows higher FSI (up to 4.0) within these influence zones and is a potentially transformative tool for affordable housing delivery — enabling high-density affordable housing in well-connected locations rather than peripheral sites.", true),
      blank(40),
      subHead("6.4 International Policy Models", 2),
      body("Singapore's mandatory CPF (Central Provident Fund) savings scheme, which channels a portion of all workers' wages into a housing savings account, has been central to achieving near-universal homeownership. Vienna's social housing model, where approximately 60% of residents live in municipally owned or subsidized housing, demonstrates the viability of large-scale public rental housing."),
      blank(40),
      subHead("6.5 Policy Gaps and Design Implications", 2),
      body("Key policy gaps with direct design implications include:"),
      bullet("The absence of mandatory minimum space standards for government-assisted housing in many states (enabling dangerously small EWS units below 25 sqm)."),
      bullet("Inadequate provisions for community infrastructure — schools, health centres, community halls — in housing scheme approvals."),
      bullet("Lack of design quality review mechanisms in government tender processes, reducing housing design to a cost-minimization exercise."),
      bullet("Insufficient long-term maintenance funding for government housing estates."),

      pageBreak(),

      // ══════════════════════════════════════════════════════════════════════
      // CHAPTER 7 — CHALLENGES
      // ══════════════════════════════════════════════════════════════════════
      chapterBanner("7", "CHALLENGES AND BARRIERS"),
      blank(60),
      body("Despite the clear need, the significant policy frameworks, and the growing body of design knowledge, affordable high-density housing delivery continues to face formidable challenges. This chapter provides a structured analysis of the principal barriers, drawing on both literature and case study evidence."),
      blank(40),
      subHead("7.1 Financial and Economic Constraints", 2),
      body("The fundamental tension in affordable housing is financial: the populations with the greatest housing need have the least ability to pay, while the private sector requires commercially viable returns. Land costs in major Indian cities have escalated so rapidly that cross-subsidization — even with high FSI and government incentives — is increasingly difficult to achieve.", true),
      blank(20),
      body("Construction costs for quality housing with adequate climate design, structural integrity, and finishes are rising. The pressure to minimize upfront costs frequently leads to compromises in build quality that generate large maintenance liabilities within 10-15 years of construction."),
      blank(40),
      subHead("7.2 Infrastructure and Service Delivery", 2),
      body("High-density housing dramatically increases the demand for infrastructure — water supply, sewage, solid waste management, electricity, roads, public transport — in proportion to the density increase. Indian cities already struggle with infrastructure deficits; adding high-density affordable housing without complementary infrastructure investment creates acute service failures.", true),
      blank(20),
      body("This challenge is particularly acute for in-situ slum rehabilitation projects, where dense new construction replaces (though rarely replicates) the informal infrastructure networks that sustained the previous settlement."),
      blank(40),
      subHead("7.3 Social Resistance and Community Issues", 2),
      body("Large-scale housing redevelopment frequently encounters social resistance from affected communities, who fear: displacement from established livelihoods, loss of social networks and community support systems, changes to housing typology that disrupt cultural practices, and inadequate compensation or resettlement.", true),
      blank(20),
      body("The history of top-down housing schemes in India — from the mass demolition of informal settlements in the Emergency period to contemporary high-rise rehabilitation projects — has generated deep community distrust of government-led housing programmes. This distrust is often a rational response to documented histories of broken promises."),
      blank(40),
      subHead("7.4 Land Acquisition and Tenure", 2),
      body("Land is the most intractable challenge in urban affordable housing delivery. Urban land in India's major cities is among the most expensive globally, controlled by a complex web of private owners, government agencies, and — most problematically — informal occupants with de facto but not de jure tenure rights.", true),
      blank(20),
      body("The Land Acquisition, Rehabilitation and Resettlement Act (LARR) 2013, while significantly strengthening the rights of those displaced, has also increased the time and cost of land assembly, deterring large-scale affordable housing projects."),
      blank(40),
      subHead("7.5 Design and Institutional Quality Constraints", 2),
      body("Perhaps the most under-discussed challenge is the systematic devaluation of design quality in affordable housing delivery. Government tender processes overwhelmingly optimize for cost, with minimal weight given to design quality, environmental performance, or liveability. Architectural fees for public housing are severely compressed, attracting less experienced practitioners and discouraging innovative design.", true),
      blank(20),
      calloutBox("Key Insight:", "The most significant challenge may be institutional: without strong, design-literate public sector institutions committed to long-term housing quality — analogous to Singapore's HDB — India's affordable housing sector will continue to generate large quantities of inadequate housing rather than the quality, liveable, high-density communities that are possible and necessary."),

      pageBreak(),

      // ══════════════════════════════════════════════════════════════════════
      // CHAPTER 8 — DESIGN PROPOSAL
      // ══════════════════════════════════════════════════════════════════════
      chapterBanner("8", "DESIGN PROPOSAL"),
      blank(60),
      body("This chapter presents the original architectural design proposal that forms the creative core of this dissertation. The proposal synthesizes the principles (Chapter 3), design strategies (Chapter 4), and case study lessons (Chapter 5) into a specific, buildable housing scheme for a rapidly urbanizing Indian city context."),
      blank(40),
      subHead("8.1 Site Selection and Analysis", 2),
      body("The proposed site is a 2.5-hectare urban infill parcel located in the peri-urban fringe of a rapidly growing Tier-2 Indian city (the proposal is applicable to cities including Coimbatore, Madurai, Nashik, or Bhubaneswar as representative contexts). The site is situated 600m from a proposed mass transit corridor, enabling TOD-compliant FSI of 3.0.", true),
      blank(20),
      body("Site Analysis highlights:"),
      bullet("Predominantly flat topography with a seasonal drainage channel along the southern edge."),
      bullet("Prevailing breeze from the south-west; predominantly hot-humid climate."),
      bullet("Existing informal settlement of 180 households to the north."),
      bullet("Government primary school and anganwadi within 400m walking distance."),
      blank(20),
      calloutBox("Site Data:", "Area: 2.5 Ha | FSI Permissible: 3.0 (TOD zone) | Max. Ground Coverage: 40% | Setbacks: 6m all sides | Total Permissible Built-up Area: 75,000 sq.m"),
      blank(40),
      subHead("8.2 Design Concept and Philosophy", 2),
      body("The design concept is titled 'The Urban Chowk' — a contemporary reinterpretation of the traditional Indian chowk (courtyard community space) as the organizing principle for high-density housing. Just as the chowk was the social, civic, and spatial heart of the traditional Indian neighbourhood, the proposed housing clusters are organized around a hierarchy of shared courtyards at multiple scales.", true),
      blank(20),
      body("The design philosophy is guided by three commitments: Density with Dignity (achieving the required density without compromising spatial quality); Community First (prioritizing shared spaces and community infrastructure); and Climate Responsiveness (achieving passive climate comfort without mechanical cooling where possible)."),
      blank(40),
      subHead("8.3 Master Plan and Spatial Organization", 2),
      body("The site is organized into three residential clusters, each containing two G+8 residential blocks arranged around a shared courtyard of approximately 900 sqm. A central community spine — a landscaped pedestrian street — connects the three clusters and anchors the community amenity zone.", true),
      blank(20),
      body("Ground Floor: 100% active frontage — small shops, community kitchen, child daycare, auto-repair workshops, and a community multipurpose hall. Upper Floors 1-8: Residential, with alternating open corridors at every 3rd floor to serve as communal semi-open spaces ('sky chowks')."),
      blank(20),
      infoTable([
        ["Zone", "Area (sqm)", "Proportion"],
        ["Residential (All Floors)", "54,000", "72%"],
        ["Ground Floor Commercial", "6,000", "8%"],
        ["Community Amenities", "4,500", "6%"],
        ["Circulation and Services", "4,500", "6%"],
        ["Open Space and Landscape", "6,000", "8%"]
      ]),
      blank(40),
      subHead("8.4 Architectural Programme and Unit Mix", 2),
      body("The proposal provides 720 dwelling units across three income categories, enabling a mixed-income community:"),
      bullet("EWS Units (25 sqm, 1-room): 216 units (30%) — subsidized, rent-to-own model."),
      bullet("LIG Units (40 sqm, 1BHK): 288 units (40%) — PMAY-linked subsidy."),
      bullet("MIG Units (60 sqm, 2BHK): 216 units (30%) — market rate (cross-subsidizes EWS)."),
      blank(20),
      body("All units are designed with: cross-ventilation (window on both external and courtyard-facing walls), balcony (minimum 4 sqm), internal toilet and kitchen, and access to the shared drying terrace on the building roof."),
      blank(40),
      subHead("8.5 Construction and Material Strategy", 2),
      body("The structural system is a reinforced concrete frame with flat slab construction, enabling flexible internal layouts and future incremental modifications. Infill walls use fly-ash AAC blocks — a cost-effective, thermally efficient, and sustainable alternative to fired clay bricks.", true),
      blank(20),
      body("The proposal targets a construction cost of approximately Rs. 2,800 per sq.ft (excluding land), achieving the EWS and LIG unit cost targets set by PMAY. A phased construction programme enables the first 240 units to be occupied within 24 months."),
      blank(40),
      subHead("8.6 Sustainability Features", 2),
      bullet("Rooftop solar PV: 120kWp across all blocks, covering 30% of common area electricity."),
      bullet("Rainwater harvesting: catchment from all roofs, stored in underground sumps."),
      bullet("Greywater treatment and reuse for landscape irrigation."),
      bullet("Native species landscape design in all courtyards."),
      bullet("Bicycle parking and pedestrian-priority internal street network."),
      blank(20),
      calloutBox("Energy Performance Target:", "The proposal targets a 40% reduction in operational energy compared to a baseline conventional housing block of equivalent area, achieved through passive design, high-performance insulation, and renewable energy generation. This aligns with the BEE (Bureau of Energy Efficiency) Energy Conservation Building Code (ECBC) Residential requirements."),

      pageBreak(),

      // ══════════════════════════════════════════════════════════════════════
      // CHAPTER 9 — CONCLUSION
      // ══════════════════════════════════════════════════════════════════════
      chapterBanner("9", "CONCLUSION"),
      blank(60),
      subHead("9.1 Summary of Key Findings", 2),
      body("This dissertation set out to explore affordable high-density housing as a critical architectural and urban response to rapid urbanization, with specific reference to the Indian context. The research has demonstrated, across its multiple analytical strands, several significant conclusions:", true),
      blank(20),
      numbered("Affordability is not a diminished form of architecture but a demanding brief that requires the full creative and intellectual resources of the discipline. The finest affordable housing — Aranya, Quinta Monroy — is also some of the finest architecture of the twentieth century."),
      numbered("High density and high quality are not mutually exclusive. Singapore's HDB estates, at densities of 800+ DPH, consistently achieve high residential satisfaction ratings. The determining factor is not density itself but the quality of spatial design, community infrastructure, and long-term management."),
      numbered("Incremental and participatory approaches consistently outperform top-down mass provision in terms of community satisfaction, social cohesion, and long-term maintenance. The architect's role in such approaches shifts from designer of dwellings to designer of frameworks."),
      numbered("Policy reform is as important as design innovation. The most elegant architectural solution is irrelevant if the policy environment, financing mechanisms, and institutional capacity to deliver and sustain affordable housing are absent."),
      numbered("Climate responsiveness in affordable housing is not a luxury — it is a necessity. In India's hot-humid climate, passive climate design directly reduces household energy expenditure (a significant affordability dimension) and improves health outcomes."),
      blank(40),
      subHead("9.2 Contributions of the Design Proposal", 2),
      body("The 'Urban Chowk' design proposal demonstrates, through specific spatial and programmatic decisions, that it is possible to achieve: 720 affordable dwelling units on 2.5 hectares at an FSI of 3.0, serving EWS, LIG, and MIG households in a mixed-income community; a rich hierarchy of shared community spaces from private balcony to public spine; a climate-responsive passive design strategy targeting 40% operational energy reduction; and economic viability through mixed-income cross-subsidization.", true),
      blank(40),
      subHead("9.3 Future Research Directions", 2),
      body("This dissertation has opened several avenues for further research:"),
      bullet("Post-occupancy evaluation of PMAY housing projects to systematically document resident experience and design outcomes."),
      bullet("Comparative study of incremental housing delivery mechanisms across different Indian state contexts."),
      bullet("Investigation of digital fabrication and modular construction technologies to reduce affordable housing construction costs in India."),
      bullet("Development of a community participation methodology specifically adapted to the Indian urban housing design process."),
      blank(40),
      body("In conclusion, affordable high-density housing is not merely a technical or economic challenge — it is one of the defining ethical and creative challenges of twenty-first century architecture. How we house the urban poor reflects and shapes the cities and societies we are. The imperative is clear: architecture must respond with intelligence, generosity, and urgency.", true),

      pageBreak(),

      // ══════════════════════════════════════════════════════════════════════
      // APPENDICES
      // ══════════════════════════════════════════════════════════════════════
      centeredBold("APPENDICES", 32, DARK_BLUE),
      rule(),
      blank(40),
      subHead("Appendix 1: Site Analysis Drawings", 2),
      body("Location Map (City scale 1:50,000), Site Plan with surrounding context (1:2,000), Solar path and wind rose diagram, Existing infrastructure and services mapping, Photographs of site and surroundings."),
      blank(40),
      subHead("Appendix 2: Design Development Drawings", 2),
      body("Master Plan (1:500), Ground Floor Plan — Community Level (1:200), Typical Residential Floor Plan (1:200), Individual Unit Plans — EWS, LIG, MIG (1:50), Building Sections (1:200), Elevations — North and South facades (1:200), Axonometric View, Perspective Renders."),
      blank(40),
      subHead("Appendix 3: Structural and Services Schematic", 2),
      body("Structural grid and column layout (indicative), Drainage and rainwater harvesting schematic, Solar PV layout on rooftops, Vertical circulation and services core diagrams."),
      blank(40),
      subHead("Appendix 4: Area Schedule and Cost Estimate", 2),
      body("Detailed area schedule by unit type and floor, Construction cost estimate (elemental), Project phasing plan, Indicative financial model for cross-subsidization."),
      blank(40),
      subHead("Appendix 5: Case Study Documentation", 2),
      body("Supplementary drawings, photographs, and data for Aranya Township, HDB Singapore, Quinta Monroy, and Dharavi Redevelopment Project, beyond what is included in Chapter 5."),

      pageBreak(),

      // ══════════════════════════════════════════════════════════════════════
      // REFERENCES
      // ══════════════════════════════════════════════════════════════════════
      centeredBold("REFERENCES", 32, DARK_BLUE),
      rule(),
      blank(40),
      body("(Listed alphabetically by first author, as per Anna University format)"),
      blank(30),
      ...[
        "Alexander, C., Ishikawa, S. and Silverstein, M. (1977) A Pattern Language: Towns, Buildings, Construction. Oxford University Press, New York.",
        "Aravena, A. and Iacobelli, A. (2016) Elemental: Incremental Housing and Participatory Design Manual. Hatje Cantz, Ostfildern.",
        "Bhan, G. (2016) In the Public's Interest: Evictions, Citizenship and Inequality in Contemporary Delhi. Orient BlackSwan, Hyderabad.",
        "Correa, C. (1985) The New Landscape: Urbanisation in the Third World. Butterworth Architecture, London.",
        "Davis, M. (2006) Planet of Slums. Verso, London.",
        "Doshi, B.V. (1989) 'Aranya Housing Development', Vastushilpa Foundation, Ahmedabad.",
        "Hall, P. (1988) Cities of Tomorrow: An Intellectual History of Urban Planning and Design since 1880. Basil Blackwell, Oxford.",
        "Housing Development Board (HDB) Singapore (2022) Annual Report 2021/2022. HDB, Singapore.",
        "Jacobs, J. (1961) The Death and Life of Great American Cities. Random House, New York.",
        "Ministry of Housing and Urban Affairs (MoHUA) (2021) Pradhan Mantri Awas Yojana — Urban: Progress Report. Government of India, New Delhi.",
        "Ministry of Housing and Urban Affairs (MoHUA) (2017) National Transit Oriented Development Policy. Government of India, New Delhi.",
        "National Housing Bank (NHB) (2022) Report on Trend and Progress of Housing in India. National Housing Bank, New Delhi.",
        "Rapoport, A. (1969) House Form and Culture. Prentice-Hall, Englewood Cliffs, NJ.",
        "Turner, J.F.C. (1976) Housing by People: Towards Autonomy in Building Environments. Marion Boyars, London.",
        "UN-Habitat (2022) World Cities Report 2022: Envisaging the Future of Cities. United Nations Human Settlements Programme, Nairobi.",
        "United Nations Department of Economic and Social Affairs (UNDESA) (2019) World Urbanization Prospects 2018. United Nations, New York.",
        "Vijayalakshmi, K. and Ramesh, M.V. (2019) 'Affordable Housing in India: Challenges and Opportunities', Journal of Urban Planning and Development, Vol. 145, No. 2, pp. 1-12.",
        "World Bank (2020) Affordable Housing Finance in India: Key Issues and Recommendations. World Bank Group, Washington DC."
      ].map(ref => new Paragraph({
        spacing: { before: 120, after: 120, line: 276 },
        indent: { left: 720, hanging: 720 },
        children: [new TextRun({ text: ref, size: 24, font: "Times New Roman", color: TEXT })]
      }))
    ]
  }]
});

// Write file
Packer.toBuffer(doc).then(buffer => {
  fs.writeFileSync('/home/claude/dissertation_outline.docx', buffer);
  console.log('Document created successfully!');
}).catch(err => console.error('Error:', err));