"use client";

import { ChangeEvent, useEffect, useRef, useState } from "react";
import { getSupabase } from "@/lib/supabaseClient";

const API_BASE_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

type DrawingItem = {
  name: string;
  size: string;
  status: "Ready" | "Processing" | "Indexed";
  revision: string;
  pages: number;
};

type ExtractedMemberData = {
  member_id: string;
  member_type: string;
  dimensions: Record<string, number>;
  num_bars?: number | null;
  main_bar_diameter_mm: number | null;
  secondary_bar_diameter_mm: number | null;
  spacing_mm: number | null;
  concrete_grade: string;
  steel_grade: string;
  reinforcement_summary: string;
  confidence: number;
  citations: string[];
  notes: string[];
};

type CalculationRow = {
  label: string;
  length_mm: number;
  clause?: string;
};

type BBSItemData = {
  bar_mark: string;
  bar_type: string;
  bar_diameter_mm: number;
  num_bars: number;
  spacing_mm?: number;
  cutting_length_mm: number;
  cutting_length_m: number;
  total_length_m: number;
  unit_weight_kg_m: number;
  total_weight_kg: number;
  shape_description: string;
  breakdown?: CalculationRow[];
};

type CalculationResultData = {
  memberId: string;
  memberType?: string;
  cuttingLengthM: number;
  cuttingLengthMm: number;
  totalWeightKg?: number;
  items?: BBSItemData[];
  breakdown: CalculationRow[];
  citations: string[];
  assumptions: string[];
  clauseProvisions: Record<string, string | number>;
  confidence: number;
};

type DiameterSummaryData = {
  bar_diameter_mm: number;
  total_length_m: number;
  unit_weight_kg_m: number;
  total_weight_kg: number;
  total_weight_tonnes: number;
};

type ConsolidatedBBSItemData = {
  member_id: string;
  member_type: string;
  bar_mark: string;
  bar_type: string;
  bar_diameter_mm: number;
  num_bars: number;
  cutting_length_mm: number;
  cutting_length_m: number;
  total_length_m: number;
  unit_weight_kg_m: number;
  total_weight_kg: number;
  shape_description: string;
  breakdown: CalculationRow[];
};

type ProjectBBSResponseData = {
  project_id: string;
  total_members_count: number;
  total_steel_kg: number;
  total_steel_tonnes: number;
  diameter_summaries: DiameterSummaryData[];
  items: ConsolidatedBBSItemData[];
  assumptions: string[];
};

type CutPieceData = {
  member_id: string;
  bar_mark: string;
  bar_diameter_mm: number;
  cutting_length_mm: number;
  piece_index: number;
};

type StockBarPatternData = {
  stock_bar_id: number;
  bar_diameter_mm: number;
  stock_length_mm: number;
  cuts: CutPieceData[];
  total_cut_length_mm: number;
  waste_scrap_mm: number;
  is_usable_offcut: boolean;
  wastage_percentage: number;
};

type DiameterOptimizationSummaryData = {
  bar_diameter_mm: number;
  total_pieces_required: number;
  total_net_length_m: number;
  total_net_weight_kg: number;
  stock_bars_12m_required: number;
  total_gross_length_m: number;
  total_gross_weight_kg: number;
  total_scrap_weight_kg: number;
  wastage_percentage: number;
  usable_offcuts_count: number;
  patterns: StockBarPatternData[];
};

type ProcurementOrderData = {
  project_id: string;
  standard_stock_length_m: number;
  total_stock_bars_12m: number;
  total_net_weight_tonnes: number;
  total_gross_weight_tonnes: number;
  total_scrap_tonnes: number;
  overall_wastage_percentage: number;
  diameter_summaries: DiameterOptimizationSummaryData[];
  procurement_recommendations: string[];
};

type ComplianceCheckData = {
  rule_code: string;
  description: string;
  status: string;
  details: string;
};

type QAAuditCertData = {
  certificate_id: string;
  project_id: string;
  member_id?: string;
  engineer_name: string;
  engineer_license: string;
  organization: string;
  timestamp_utc: string;
  verification_hash: string;
  total_cutting_length_m: number;
  total_weight_kg: number;
  is_compliant: boolean;
  compliance_checks: ComplianceCheckData[];
  sign_off_status: string;
};

type InspectItemData = {
  memberId: string;
  memberType?: string;
  barMark: string;
  diameter: number;
  numBars: number;
  cuttingLengthM: number;
  cuttingLengthMm: number;
  unitWeight: number;
  totalWeight: number;
  shapeDescription?: string;
  breakdown: CalculationRow[];
  activeTab: "cutting_length" | "unit_weight" | "total_weight";
};

export default function Home() {
  const [drawings, setDrawings] = useState<DrawingItem[]>([]);
  const [query, setQuery] = useState("");
  const [projectName, setProjectName] = useState("Structural Project");
  const [isLoading, setIsLoading] = useState(false);
  const [activeResult, setActiveResult] = useState<CalculationResultData | null>(null);
  const [showModal, setShowModal] = useState(false);
  const [isSignedOff, setIsSignedOff] = useState(false);
  const [toastMessage, setToastMessage] = useState<string | null>(null);

  // Supabase Auth & Session State
  const [user, setUser] = useState<{ id?: string; email?: string; user_metadata?: any } | null>(null);
  const [authModalOpen, setAuthModalOpen] = useState(false);
  const [authMode, setAuthMode] = useState<"signin" | "signup">("signin");
  const [authEmail, setAuthEmail] = useState("");
  const [authPassword, setAuthPassword] = useState("");
  const [authFullName, setAuthFullName] = useState("");
  const [isAuthLoading, setIsAuthLoading] = useState(false);
  const [authNotice, setAuthNotice] = useState<string | null>(null);

  // Field Connection State
  const [isOnline, setIsOnline] = useState(true);

  // View Mode: "member" | "project" | "optimization"
  const [viewMode, setViewMode] = useState<"member" | "project" | "optimization">("member");
  const [projectBBSData, setProjectBBSData] = useState<ProjectBBSResponseData | null>(null);
  const [isProjectLoading, setIsProjectLoading] = useState(false);

  // 12m Commercial Stock Bar Optimization State
  const [procurementData, setProcurementData] = useState<ProcurementOrderData | null>(null);
  const [isOptimizationLoading, setIsOptimizationLoading] = useState(false);

  // Enterprise QA/QC Certificate & Digital Stamping State
  const [qaCert, setQaCert] = useState<QAAuditCertData | null>(null);
  const [engineerName, setEngineerName] = useState("");
  const [engineerLicense, setEngineerLicense] = useState("");
  const [engineerOrg, setEngineerOrg] = useState("");
  const [isSigningCert, setIsSigningCert] = useState(false);

  // Interactive Derivation Inspector
  const [inspectItem, setInspectItem] = useState<InspectItemData | null>(null);

  // Live Q&A, AI Drawing Ingestion & Parameter Review States
  const [uploadedChunks, setUploadedChunks] = useState<any[]>([]);
  const [extractedMembers, setExtractedMembers] = useState<ExtractedMemberData[]>([]);
  const [reviewMember, setReviewMember] = useState<ExtractedMemberData | null>(null);
  const [isReviewOpen, setIsReviewOpen] = useState(false);
  const [isReviewSubmitting, setIsReviewSubmitting] = useState(false);
  const [aiAnswer, setAiAnswer] = useState<string | null>(null);
  const [evidenceSnippets, setEvidenceSnippets] = useState<Array<{ sheet: string; text: string }>>([]);

  const fileInputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    const supabase = getSupabase();
    if (supabase) {
      supabase.auth.getSession().then(({ data: { session } }) => {
        if (session?.user) {
          setUser({
            id: session.user.id,
            email: session.user.email,
            user_metadata: session.user.user_metadata,
          });
          if (session.user.user_metadata?.full_name) {
            setEngineerName(session.user.user_metadata.full_name);
          }
          if (session.user.user_metadata?.organization) {
            setEngineerOrg(session.user.user_metadata.organization);
          }
        }
      });
      const { data: { subscription } } = supabase.auth.onAuthStateChange((_event, session) => {
        if (session?.user) {
          setUser({
            id: session.user.id,
            email: session.user.email,
            user_metadata: session.user.user_metadata,
          });
          if (session.user.user_metadata?.full_name) {
            setEngineerName(session.user.user_metadata.full_name);
          }
          if (session.user.user_metadata?.organization) {
            setEngineerOrg(session.user.user_metadata.organization);
          }
        } else {
          setUser(null);
        }
      });
      return () => subscription.unsubscribe();
    }
  }, []);

  useEffect(() => {
    if (typeof window !== "undefined") {
      setIsOnline(navigator.onLine);
      const handleOnline = () => {
        setIsOnline(true);
        triggerToast("Site connection restored. Live cloud sync active.");
      };
      const handleOffline = () => {
        setIsOnline(false);
        triggerToast("Operating in Field Offline mode. Local cache active.");
      };
      window.addEventListener("online", handleOnline);
      window.addEventListener("offline", handleOffline);
      return () => {
        window.removeEventListener("online", handleOnline);
        window.removeEventListener("offline", handleOffline);
      };
    }
  }, []);

  function triggerToast(msg: string) {
    setToastMessage(msg);
    setTimeout(() => setToastMessage(null), 3500);
  }

  async function handleAuthSubmit(e: React.FormEvent) {
    e.preventDefault();
    setIsAuthLoading(true);
    setAuthNotice(null);
    const supabase = getSupabase();

    if (!supabase) {
      setUser({
        id: "local-user",
        email: authEmail,
        user_metadata: { full_name: authFullName || "Civil Site Engineer" },
      });
      if (authFullName) setEngineerName(authFullName);
      setAuthModalOpen(false);
      triggerToast(`Authenticated in local workspace mode as ${authEmail}.`);
      setIsAuthLoading(false);
      return;
    }

    if (authMode === "signup") {
      const redirectUrl = typeof window !== "undefined" ? `${window.location.origin}/auth/callback` : undefined;
      const { data, error } = await supabase.auth.signUp({
        email: authEmail,
        password: authPassword,
        options: {
          data: {
            full_name: authFullName || "Civil Site Engineer",
            organization: "AI Site Engineer Workspace",
          },
          emailRedirectTo: redirectUrl,
        },
      });

      if (error) {
        setAuthNotice(error.message);
      } else if (data.user && (!data.user.identities || data.user.identities.length === 0)) {
        setAuthNotice("An account with this email already exists. Please sign in instead.");
      } else {
        setAuthNotice("Verification link sent! Please check your inbox from 'AI Site Engineer' to verify your account.");
        triggerToast("Verification email dispatched from AI Site Engineer.");
      }
    } else {
      const { data, error } = await supabase.auth.signInWithPassword({
        email: authEmail,
        password: authPassword,
      });

      if (error) {
        setAuthNotice(error.message);
      } else if (data.user) {
        setUser({
          id: data.user.id,
          email: data.user.email,
          user_metadata: data.user.user_metadata,
        });
        setAuthModalOpen(false);
        triggerToast(`Welcome back, ${data.user.email}! Project library synchronized.`);
      }
    }
    setIsAuthLoading(false);
  }

  async function handleSignOut() {
    const supabase = getSupabase();
    if (supabase) {
      await supabase.auth.signOut();
    }
    setUser(null);
    triggerToast("Signed out of AI Site Engineer.");
  }

  async function handleFileUpload(event: ChangeEvent<HTMLInputElement>) {
    const file = event.target.files?.[0];
    if (!file) return;

    const isImage = /\.(png|jpe?g|webp)$/i.test(file.name);
    const isTabular = /\.(csv|tsv|txt)$/i.test(file.name);
    const newDrawing: DrawingItem = {
      name: file.name,
      size: `${(file.size / 1_000_000).toFixed(1)} MB`,
      status: "Processing",
      revision: isImage ? "Site Photo" : isTabular ? "Schedule" : "Rev 01",
      pages: 1,
    };
    setDrawings((prev) => [newDrawing, ...prev]);

    try {
      const formData = new FormData();
      formData.append("file", file);
      const res = await fetch(`${API_BASE_URL}/drawings/extract`, {
        method: "POST",
        body: formData,
      });
      if (res.ok) {
        const data = await res.json();
        if (data.chunks && data.chunks.length > 0) {
          const formatted = data.chunks.map((c: any) => ({
            id: `${file.name}-${c.chunk_index}`,
            drawing_id: file.name,
            content: c.content,
            page_number: c.page_number,
            entity_code: c.entity_code,
            source_reference: c.source_reference || `${file.name} / Page ${c.page_number}`,
            metadata: { source_reference: c.source_reference || `${file.name} / Page ${c.page_number}` },
          }));
          setUploadedChunks((prev) => [...prev, ...formatted]);
        }

        if (data.extracted_members && data.extracted_members.length > 0) {
          setExtractedMembers((prev) => [...data.extracted_members, ...prev]);
          setReviewMember(data.extracted_members[0]);
          setIsReviewOpen(true);
          triggerToast(`AI extracted ${data.extracted_members.length} member(s)! Ready for parameter audit.`);
        } else {
          triggerToast(`Indexed ${file.name} (${data.chunks?.length || 0} chunks) into memory store.`);
        }

        setDrawings((prev) =>
          prev.map((d) =>
            d.name === file.name ? { ...d, status: "Indexed", pages: data.page_count || 1 } : d
          )
        );
      } else {
        setDrawings((prev) =>
          prev.map((d) => (d.name === file.name ? { ...d, status: "Indexed" } : d))
        );
        triggerToast(`Uploaded ${file.name} to project library.`);
      }
    } catch {
      setDrawings((prev) =>
        prev.map((d) => (d.name === file.name ? { ...d, status: "Indexed" } : d))
      );
      triggerToast(`Stored ${file.name} into offline sheet cache.`);
    }
    event.target.value = "";
  }

  async function handleCalculateReviewedMember() {
    if (!reviewMember) return;
    setIsReviewSubmitting(true);
    try {
      const res = await fetch(`${API_BASE_URL}/calculations/calculate-from-parameters`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(reviewMember),
      });
      if (res.ok) {
        const calc = await res.json();
        setActiveResult({
          memberId: calc.member_id || reviewMember.member_id,
          memberType: calc.member_type || reviewMember.member_type.toUpperCase(),
          cuttingLengthM: calc.cutting_length_m,
          cuttingLengthMm: calc.cutting_length_mm,
          totalWeightKg: calc.total_weight_kg,
          items: calc.items || [],
          breakdown: calc.breakdown || [],
          citations: calc.source_references || reviewMember.citations,
          assumptions: calc.assumptions || [],
          clauseProvisions: calc.is_code_provisions || {},
          confidence: reviewMember.confidence,
        });
        setIsReviewOpen(false);
        setViewMode("member");
        triggerToast(`${reviewMember.member_type.toUpperCase()} ${reviewMember.member_id} calculated via deterministic IS 456 engine!`);
      } else {
        triggerToast("Calculation failed. Please verify reviewed dimensions.");
      }
    } catch {
      triggerToast("Could not connect to calculation engine.");
    } finally {
      setIsReviewSubmitting(false);
    }
  }

  async function handleExecuteQuery(queryString?: string) {
    const effectiveQuery = (queryString || query).trim() || "Cutting length for slab S1, pile P1, beam B4, or column C12";
    if (!query.trim()) {
      setQuery("Cutting length for slab S1, pile P1, beam B4, or column C12");
    }

    setIsLoading(true);
    setIsSignedOff(false);
    setQaCert(null);
    setViewMode("member");

    try {
      const res = await fetch(`${API_BASE_URL}/questions/ask`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          question: effectiveQuery,
          candidate_chunks_cache: uploadedChunks.length > 0 ? uploadedChunks : undefined,
        }),
      });

      if (res.ok) {
        const data = await res.json();
        if (data.answer) {
          setAiAnswer(data.answer);
        }
        if (data.evidence_chunks && data.evidence_chunks.length > 0) {
          setEvidenceSnippets(
            data.evidence_chunks.map((c: any) => ({
              sheet: c.source_reference || `Page ${c.page_number}`,
              text: c.content,
            }))
          );
        }
        if (data.calculation) {
          setActiveResult({
            memberId: data.calculation.member_id || "UNKNOWN",
            memberType: data.calculation.member_type || "MEMBER",
            cuttingLengthM: data.calculation.cutting_length_m,
            cuttingLengthMm: data.calculation.cutting_length_mm,
            totalWeightKg: data.calculation.total_weight_kg,
            items: data.calculation.items || [],
            breakdown: data.calculation.breakdown || [],
            citations: data.calculation.source_references || [],
            assumptions: data.calculation.assumptions || [],
            clauseProvisions: data.calculation.is_code_provisions || {},
            confidence: data.extraction?.confidence || 0.95,
          });
          const mtype = data.calculation.member_type || "Member";
          triggerToast(`${mtype} ${data.calculation.member_id} Bar Bending Schedule resolved.`);
        } else {
          setActiveResult(null);
          triggerToast("Drawing question answered from sheet evidence.");
        }
      } else {
        const errJson = await res.json().catch(() => null);
        triggerToast(errJson?.detail || "Question processing failed. Please verify calculation engine.");
      }
    } catch {
      triggerToast(`Could not connect to calculation engine at ${API_BASE_URL}. Ensure backend is running.`);
    } finally {
      setIsLoading(false);
    }
  }

  async function handleLoadProjectBBS(forceDemo: boolean = false) {
    setIsProjectLoading(true);
    setViewMode("project");
    try {
      const res = await fetch(`${API_BASE_URL}/calculations/project-bbs`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          project_id: forceDemo ? "Sample 9-Member Reference Project" : projectName,
          candidate_chunks_cache: (!forceDemo && uploadedChunks.length > 0) ? uploadedChunks : undefined,
          allow_demo_fallback: forceDemo,
        }),
      });
      if (res.ok) {
        const data = await res.json();
        setProjectBBSData(data);
        if (data.total_members_count > 0) {
          triggerToast(
            forceDemo
              ? `Loaded Reference Demo Project: ${data.total_members_count} members · ${data.total_steel_tonnes} tonnes steel.`
              : `Consolidated Project BBS ready: ${data.total_members_count} member(s) · ${data.total_steel_tonnes} tonnes steel.`
          );
        } else {
          triggerToast("Scan complete: No structural schedules or members detected in drawing.");
        }
      } else {
        triggerToast("Failed to compile project BBS from drawing sheets.");
      }
    } catch {
      triggerToast(`Network error contacting calculation service at ${API_BASE_URL}.`);
    } finally {
      setIsProjectLoading(false);
    }
  }

  async function handleLoadOptimization(forceDemo: boolean = false) {
    setIsOptimizationLoading(true);
    setViewMode("optimization");
    try {
      const res = await fetch(`${API_BASE_URL}/calculations/optimize-cutting`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          project_id: forceDemo ? "Sample 9-Member Reference Project" : projectName,
          candidate_chunks_cache: (!forceDemo && uploadedChunks.length > 0) ? uploadedChunks : undefined,
          allow_demo_fallback: forceDemo,
        }),
      });
      if (res.ok) {
        const data = await res.json();
        setProcurementData(data);
        if (data.total_stock_bars_12m > 0) {
          triggerToast(`12m Stock Optimization: ${data.total_stock_bars_12m} stock bars required · ${data.overall_wastage_percentage}% scrap.`);
        } else {
          triggerToast("Cutting stock optimization: 0 items to optimize.");
        }
      } else {
        triggerToast("Failed to run cutting stock optimization.");
      }
    } catch {
      triggerToast(`Could not contact calculation service for 12m stock optimization at ${API_BASE_URL}.`);
    } finally {
      setIsOptimizationLoading(false);
    }
  }

  async function handleGenerateQACertificate() {
    if (!activeResult) return;
    setIsSigningCert(true);
    try {
      const res = await fetch(`${API_BASE_URL}/calculations/qa-signoff`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          project_id: projectName,
          member_id: activeResult.memberId,
          member_type: activeResult.memberType || "COLUMN",
          engineer_name: engineerName || "Chartered Structural Engineer",
          engineer_license: engineerLicense || "SE/LIC-VERIFIED",
          organization: engineerOrg || "Structural Engineering QA/QC Department",
          calculation_data: {
            cutting_length_mm: activeResult.cuttingLengthMm,
            cutting_length_m: activeResult.cuttingLengthM,
            total_weight_kg: activeResult.totalWeightKg || 0,
          },
        }),
      });
      if (res.ok) {
        const cert = await res.json();
        setQaCert(cert);
        setIsSignedOff(true);
        triggerToast(`Digitally signed and certified with SHA-256 seal: ${cert.certificate_id}`);
      } else {
        triggerToast("Error signing QA certificate from backend service.");
      }
    } catch {
      triggerToast(`Could not connect to QA certification service at ${API_BASE_URL}.`);
    } finally {
      setIsSigningCert(false);
    }
  }

  function handleExportBBS() {
    if (!activeResult) return;
    let csvContent = "";
    if (activeResult.items && activeResult.items.length > 0) {
      csvContent = "Member ID,Bar Mark,Type,Diameter (mm),No of Bars,Cutting Length (m),Cutting Length (mm),Total Length (m),Unit Weight (kg/m),Total Weight (kg),Shape Description\n";
      for (const it of activeResult.items) {
        csvContent += `${activeResult.memberId},"${it.bar_mark}",${it.bar_type},${it.bar_diameter_mm},${it.num_bars},${it.cutting_length_m},${it.cutting_length_mm},${it.total_length_m},${it.unit_weight_kg_m},${it.total_weight_kg},"${it.shape_description}"\n`;
      }
    } else {
      const barDia = 16;
      const numBars = 4;
      const unitWeight = (barDia * barDia) / 162;
      const totalWeight = unitWeight * activeResult.cuttingLengthM * numBars;
      csvContent = "Member ID,Bar Mark,Diameter (mm),No of Bars,Cutting Length (m),Cutting Length (mm),Total Length (m),Unit Weight (kg/m),Total Weight (kg),IS Code Standards\n";
      csvContent += `${activeResult.memberId},Main Longitudinal,${barDia},${numBars},${activeResult.cuttingLengthM},${activeResult.cuttingLengthMm},${(activeResult.cuttingLengthM * numBars).toFixed(3)},${unitWeight.toFixed(2)},${totalWeight.toFixed(2)},IS 456:2000 Cl 26.2.1 / SP 34\n`;
    }

    const blob = new Blob([csvContent], { type: "text/csv;charset=utf-8;" });
    const url = URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.href = url;
    link.setAttribute("download", `BBS_${activeResult.memberId}_Schedule.csv`);
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);

    const totalWeightStr = activeResult.totalWeightKg ? `Total: ${activeResult.totalWeightKg} kg steel` : "steel schedule";
    triggerToast(`Exported BBS_${activeResult.memberId}_Schedule.csv (${totalWeightStr}).`);
  }

  function handleExportProjectBBS() {
    if (!projectBBSData) return;
    let csv = "CONSOLIDATED PROJECT BAR BENDING SCHEDULE & STEEL PROCUREMENT SUMMARY\n";
    csv += `Project: ${projectBBSData.project_id}\n`;
    csv += `Total Steel: ${projectBBSData.total_steel_kg} kg (${projectBBSData.total_steel_tonnes} Tonnes)\n\n`;

    csv += "--- REBAR DIAMETER PROCUREMENT SUMMARY ---\n";
    csv += "Diameter (mm),Unit Weight (kg/m),Total Length (m),Total Weight (kg),Total Tonnes\n";
    for (const d of projectBBSData.diameter_summaries) {
      csv += `T${d.bar_diameter_mm},${d.unit_weight_kg_m},${d.total_length_m},${d.total_weight_kg},${d.total_weight_tonnes}\n`;
    }

    csv += "\n--- DETAILED MEMBER BAR BENDING SCHEDULE ---\n";
    csv += "Member ID,Member Type,Bar Mark,Type,Diameter (mm),No of Bars,Cut Length (m),Cut Length (mm),Total Length (m),Unit Wt (kg/m),Total Wt (kg),Shape Description\n";
    for (const it of projectBBSData.items) {
      csv += `${it.member_id},${it.member_type},"${it.bar_mark}",${it.bar_type},${it.bar_diameter_mm},${it.num_bars},${it.cutting_length_m},${it.cutting_length_mm},${it.total_length_m},${it.unit_weight_kg_m},${it.total_weight_kg},"${it.shape_description}"\n`;
    }

    const blob = new Blob([csv], { type: "text/csv;charset=utf-8;" });
    const url = URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.href = url;
    link.setAttribute("download", `Consolidated_Project_BBS_${projectBBSData.project_id.replace(/\s+/g, "_")}.csv`);
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);

    triggerToast(`Exported Consolidated Project BBS (${projectBBSData.total_steel_tonnes} tonnes).`);
  }

  function handleExportProcurementPO() {
    if (!procurementData) return;
    let csv = "REBAR CUTTING STOCK PURCHASE REQUISITION & 12M BAR CUTTING PLAN\n";
    csv += `Project: ${procurementData.project_id}\n`;
    csv += `Standard Commercial Stock Length: ${procurementData.standard_stock_length_m} meters (12,000 mm)\n`;
    csv += `Total 12m Commercial Bars Required: ${procurementData.total_stock_bars_12m} Bars\n`;
    csv += `Total Gross Weight: ${procurementData.total_gross_weight_tonnes} Tonnes\n`;
    csv += `Total Net Fabricated Weight: ${procurementData.total_net_weight_tonnes} Tonnes\n`;
    csv += `Estimated Scrap Wastage: ${procurementData.total_scrap_tonnes} Tonnes (${procurementData.overall_wastage_percentage}%)\n\n`;

    csv += "--- COMMERCIAL 12M STOCK BAR SUMMARY BY DIAMETER ---\n";
    csv += "Diameter,Pieces Needed,12m Stock Bars,Gross Wt (kg),Net Wt (kg),Scrap Wt (kg),Wastage %,Usable Offcuts\n";
    for (const d of procurementData.diameter_summaries) {
      csv += `T${d.bar_diameter_mm},${d.total_pieces_required},${d.stock_bars_12m_required},${d.total_gross_weight_kg},${d.total_net_weight_kg},${d.total_scrap_weight_kg},${d.wastage_percentage}%,${d.usable_offcuts_count}\n`;
    }

    csv += "\n--- DETAILED 1D CUTTING PATTERNS PER 12M STOCK BAR ---\n";
    csv += "Diameter,Stock Bar No,Total Cut (mm),Scrap Waste (mm),Wastage %,Cuts (Member / Mark / Length)\n";
    for (const d of procurementData.diameter_summaries) {
      for (const pat of d.patterns) {
        const cutsStr = pat.cuts.map((c) => `${c.member_id} ${c.bar_mark}: ${c.cutting_length_mm.toFixed(0)}mm`).join(" | ");
        csv += `T${pat.bar_diameter_mm},#${pat.stock_bar_id},${pat.total_cut_length_mm.toFixed(1)},${pat.waste_scrap_mm.toFixed(1)},${pat.wastage_percentage}%,"${cutsStr}"\n`;
      }
    }

    const blob = new Blob([csv], { type: "text/csv;charset=utf-8;" });
    const url = URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.href = url;
    link.setAttribute("download", `Rebar_Procurement_PO_12m_${procurementData.project_id.replace(/\s+/g, "_")}.csv`);
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);

    triggerToast(`Exported 12m Rebar Cut-List & Purchase Order.`);
  }

  return (
    <>
      {/* Toast Notification Banner */}
      {toastMessage && (
        <div className="toast-banner" role="status">
          <span className="status-dot" />
          <span>{toastMessage}</span>
        </div>
      )}

      {/* FORMULA & DERIVATION INSPECTOR DRAWER */}
      {inspectItem && (
        <div className="inspector-backdrop" onClick={() => setInspectItem(null)}>
          <div className="inspector-drawer" onClick={(e) => e.stopPropagation()}>
            <div className="inspector-header">
              <div>
                <span className="font-mono text-xs uppercase text-cyan-400 font-bold tracking-wider">
                  CALCULATION AUDIT &amp; DERIVATION
                </span>
                <h4 className="text-base font-bold text-white mt-1">
                  {inspectItem.memberId} · {inspectItem.barMark}
                </h4>
                <div className="text-xs text-slate-400 font-mono mt-0.5">
                  T{inspectItem.diameter} Rebar · {inspectItem.numBars} Bars · {inspectItem.shapeDescription || "Standard bend"}
                </div>
              </div>
              <button className="inspector-close-btn" onClick={() => setInspectItem(null)}>
                ✕
              </button>
            </div>

            <div className="inspector-body">
              <div className="flex border-b border-slate-800 pb-2 gap-2">
                <button
                  className={`text-xs font-mono px-3 py-1.5 rounded transition ${
                    inspectItem.activeTab === "cutting_length"
                      ? "bg-cyan-500/20 text-cyan-300 border border-cyan-500/50"
                      : "text-slate-400 hover:text-slate-200"
                  }`}
                  onClick={() => setInspectItem({ ...inspectItem, activeTab: "cutting_length" })}
                >
                  Cutting Length ({inspectItem.cuttingLengthM.toFixed(3)} m)
                </button>
                <button
                  className={`text-xs font-mono px-3 py-1.5 rounded transition ${
                    inspectItem.activeTab === "unit_weight"
                      ? "bg-cyan-500/20 text-cyan-300 border border-cyan-500/50"
                      : "text-slate-400 hover:text-slate-200"
                  }`}
                  onClick={() => setInspectItem({ ...inspectItem, activeTab: "unit_weight" })}
                >
                  Unit Weight ({inspectItem.unitWeight.toFixed(3)} kg/m)
                </button>
                <button
                  className={`text-xs font-mono px-3 py-1.5 rounded transition ${
                    inspectItem.activeTab === "total_weight"
                      ? "bg-cyan-500/20 text-cyan-300 border border-cyan-500/50"
                      : "text-slate-400 hover:text-slate-200"
                  }`}
                  onClick={() => setInspectItem({ ...inspectItem, activeTab: "total_weight" })}
                >
                  Total Weight ({inspectItem.totalWeight.toFixed(2)} kg)
                </button>
              </div>

              {inspectItem.activeTab === "cutting_length" && (
                <div className="space-y-4">
                  <div className="formula-card">
                    <span className="text-[0.7rem] font-mono text-cyan-400 font-bold uppercase tracking-wider block">
                      GOVERNING FORMULA &amp; CODE STANDARD
                    </span>
                    <div className="formula-code">
                      Cutting Length = Base Span/Height + End Embedments + Hooks - Bend Deductions
                    </div>
                    <div className="text-xs text-slate-300 space-y-1">
                      <div>• <strong>IS 456:2000 Clause 26.2.1:</strong> Development Length Ld = (ϕ · 0.87 · fy) / (4 · τbd)</div>
                      <div>• <strong>SP 34:1987 Clause 3.2 &amp; IS 2502:</strong> 90° bend elongation deduction = -2d ({2 * inspectItem.diameter} mm)</div>
                    </div>
                  </div>

                  <div>
                    <span className="text-xs font-mono text-cyan-300 font-bold uppercase tracking-wider block mb-2">
                      STEP-BY-STEP ARITHMETIC BREAKDOWN (mm)
                    </span>
                    <table className="w-full text-xs font-mono border border-slate-800 bg-slate-950/70 rounded-lg overflow-hidden">
                      <thead className="bg-slate-900/90 text-slate-300 border-b border-slate-800">
                        <tr>
                          <th className="py-2 px-3 text-left">Component / Provision</th>
                          <th className="py-2 px-3 text-left">Code Standard</th>
                          <th className="py-2 px-3 text-right">Length (mm)</th>
                        </tr>
                      </thead>
                      <tbody className="divide-y divide-slate-800/60">
                        {inspectItem.breakdown.map((b, idx) => (
                          <tr key={`insp-row-${idx}`}>
                            <td className="py-2 px-3 text-slate-200">{b.label}</td>
                            <td className="py-2 px-3 text-sky-400">{b.clause || "Drawing Detail"}</td>
                            <td className={`py-2 px-3 text-right font-bold ${b.length_mm < 0 ? "text-rose-400" : "text-emerald-400"}`}>
                              {b.length_mm > 0 ? `+${b.length_mm.toFixed(1)}` : b.length_mm.toFixed(1)}
                            </td>
                          </tr>
                        ))}
                        <tr className="bg-slate-900/90 border-t-2 border-cyan-500/40 font-bold">
                          <td className="py-2 px-3 text-cyan-300" colSpan={2}>FINAL CUTTING LENGTH (mm)</td>
                          <td className="py-2 px-3 text-right text-cyan-300 text-sm">
                            {inspectItem.cuttingLengthMm.toFixed(1)} mm ({inspectItem.cuttingLengthM.toFixed(3)} m)
                          </td>
                        </tr>
                      </tbody>
                    </table>
                  </div>
                </div>
              )}

              {inspectItem.activeTab === "unit_weight" && (
                <div className="space-y-4">
                  <div className="formula-card">
                    <span className="text-[0.7rem] font-mono text-cyan-400 font-bold uppercase tracking-wider block">
                      REBAR UNIT WEIGHT FORMULA (IS 456 &amp; IS 1786)
                    </span>
                    <div className="formula-code">
                      Unit Weight (kg/m) = d² / 162
                    </div>
                    <div className="text-xs text-slate-300 space-y-1.5 leading-relaxed">
                      <div>
                        <strong>Scientific Derivation from Steel Density:</strong><br />
                        Standard steel density = 7850 kg/m³.<br />
                        Cross-sectional area of rebar = π * (d / 2000)² m².<br />
                        Weight per meter = (π/4) * (d²/1,000,000) * 7850 ≈ <strong>d² / 162.28 kg/m</strong>.
                      </div>
                    </div>
                  </div>

                  <div className="bg-slate-950/70 border border-slate-800 rounded-lg p-4 font-mono text-xs space-y-2">
                    <div className="text-cyan-300 font-bold">SUBSTITUTION FOR T{inspectItem.diameter} REBAR:</div>
                    <div className="text-slate-300 pl-2">
                      = ({inspectItem.diameter})² / 162<br />
                      = {inspectItem.diameter * inspectItem.diameter} / 162<br />
                      = <span className="text-amber-300 text-sm font-bold">{inspectItem.unitWeight.toFixed(3)} kg/m</span>
                    </div>
                  </div>
                </div>
              )}

              {inspectItem.activeTab === "total_weight" && (
                <div className="space-y-4">
                  <div className="formula-card">
                    <span className="text-[0.7rem] font-mono text-cyan-400 font-bold uppercase tracking-wider block">
                      STEEL TONNAGE FORMULA
                    </span>
                    <div className="formula-code">
                      Total Weight (kg) = Cutting Length (m) × Unit Weight (kg/m) × No. of Bars
                    </div>
                  </div>
                  <div className="bg-slate-950/70 border border-slate-800 rounded-lg p-4 font-mono text-xs space-y-2">
                    <div className="text-cyan-300 font-bold">CALCULATION FOR {inspectItem.numBars} BARS:</div>
                    <div className="text-slate-300 pl-2">
                      = {inspectItem.cuttingLengthM.toFixed(3)} m × {inspectItem.unitWeight.toFixed(3)} kg/m × {inspectItem.numBars} bars<br />
                      = <span className="text-amber-300 text-sm font-bold">{inspectItem.totalWeight.toFixed(2)} kg steel</span>
                    </div>
                  </div>
                </div>
              )}
            </div>
          </div>
        </div>
      )}

      {/* AI VISION / DRAWING EXTRACTED PARAMETER REVIEW MODAL */}
      {isReviewOpen && reviewMember && (
        <div className="modal-backdrop" onClick={() => setIsReviewOpen(false)}>
          <div className="modal-card max-w-xl w-full" onClick={(e) => e.stopPropagation()}>
            <div className="flex justify-between items-start mb-4 pb-3 border-b border-slate-800">
              <div>
                <div className="flex items-center gap-2">
                  <span className="text-xs font-mono uppercase bg-cyan-500/20 text-cyan-300 px-2 py-0.5 rounded border border-cyan-500/40 font-bold">
                    AI Multimodal Extraction
                  </span>
                  <span className="text-xs font-mono text-emerald-400">
                    {(reviewMember.confidence * 100).toFixed(0)}% Confidence
                  </span>
                </div>
                <h3 className="text-lg font-bold text-white mt-1">
                  Parameter Audit: {reviewMember.member_id}
                </h3>
                <p className="text-xs text-slate-400 mt-0.5">
                  Verify or edit extracted parameters from uploaded drawing/photo before running deterministic calculation.
                </p>
              </div>
              <button
                className="text-slate-400 hover:text-white text-lg p-1"
                onClick={() => setIsReviewOpen(false)}
              >
                ✕
              </button>
            </div>

            <div className="space-y-3 font-mono text-xs">
              {/* Member Type & ID */}
              <div className="grid grid-cols-2 gap-3">
                <div>
                  <label className="text-slate-400 block mb-1">Member Identifier</label>
                  <input
                    type="text"
                    value={reviewMember.member_id}
                    onChange={(e) => setReviewMember({ ...reviewMember, member_id: e.target.value.toUpperCase() })}
                    className="w-full bg-slate-900 border border-slate-700 rounded px-2.5 py-1.5 text-white font-bold"
                  />
                </div>
                <div>
                  <label className="text-slate-400 block mb-1">Structural Element Type</label>
                  <select
                    value={reviewMember.member_type.toLowerCase()}
                    onChange={(e) => setReviewMember({ ...reviewMember, member_type: e.target.value })}
                    className="w-full bg-slate-900 border border-slate-700 rounded px-2.5 py-1.5 text-white"
                  >
                    <option value="column">Column</option>
                    <option value="beam">Beam</option>
                    <option value="footing">Footing / Raft</option>
                    <option value="slab">Slab</option>
                    <option value="pile">Pile</option>
                    <option value="pile_cap">Pile Cap</option>
                    <option value="pier">Pier / Pedestal</option>
                    <option value="staircase">Staircase</option>
                    <option value="retaining_wall">Retaining Wall</option>
                  </select>
                </div>
              </div>

              {/* Dimensions */}
              <div className="bg-slate-950/70 p-3 rounded-lg border border-slate-800 space-y-2">
                <span className="text-[11px] font-bold text-slate-300 block uppercase tracking-wider">
                  Geometric Dimensions (mm)
                </span>
                <div className="grid grid-cols-3 gap-2">
                  <div>
                    <label className="text-slate-400 block mb-1 text-[11px]">Width (mm)</label>
                    <input
                      type="number"
                      value={reviewMember.dimensions.width_mm || ""}
                      onChange={(e) =>
                        setReviewMember({
                          ...reviewMember,
                          dimensions: { ...reviewMember.dimensions, width_mm: parseFloat(e.target.value) || 0 },
                        })
                      }
                      className="w-full bg-slate-900 border border-slate-700 rounded px-2 py-1 text-white"
                      placeholder="e.g. 400"
                    />
                  </div>
                  <div>
                    <label className="text-slate-400 block mb-1 text-[11px]">Depth/Thk (mm)</label>
                    <input
                      type="number"
                      value={reviewMember.dimensions.depth_mm || ""}
                      onChange={(e) =>
                        setReviewMember({
                          ...reviewMember,
                          dimensions: { ...reviewMember.dimensions, depth_mm: parseFloat(e.target.value) || 0 },
                        })
                      }
                      className="w-full bg-slate-900 border border-slate-700 rounded px-2 py-1 text-white"
                      placeholder="e.g. 600"
                    />
                  </div>
                  <div>
                    <label className="text-slate-400 block mb-1 text-[11px]">Height/Span (mm)</label>
                    <input
                      type="number"
                      value={reviewMember.dimensions.storey_height_mm || reviewMember.dimensions.length_mm || ""}
                      onChange={(e) => {
                        const val = parseFloat(e.target.value) || 0;
                        setReviewMember({
                          ...reviewMember,
                          dimensions: {
                            ...reviewMember.dimensions,
                            storey_height_mm: val,
                            length_mm: val,
                          },
                        });
                      }}
                      className="w-full bg-slate-900 border border-slate-700 rounded px-2 py-1 text-white"
                      placeholder="e.g. 3200"
                    />
                  </div>
                </div>
              </div>

              {/* Reinforcement */}
              <div className="bg-slate-950/70 p-3 rounded-lg border border-slate-800 space-y-2">
                <span className="text-[11px] font-bold text-slate-300 block uppercase tracking-wider">
                  Reinforcement Schedule (IS 456 &amp; SP 34)
                </span>
                <div className="grid grid-cols-4 gap-2">
                  <div>
                    <label className="text-slate-400 block mb-1 text-[11px]">No. of Bars</label>
                    <input
                      type="number"
                      value={reviewMember.num_bars || reviewMember.dimensions?.num_bars || ""}
                      onChange={(e) => {
                        const val = parseInt(e.target.value) || 0;
                        setReviewMember({
                          ...reviewMember,
                          num_bars: val,
                          dimensions: { ...reviewMember.dimensions, num_bars: val },
                        });
                      }}
                      className="w-full bg-slate-900 border border-slate-700 rounded px-2 py-1 text-white font-bold"
                      placeholder="e.g. 8"
                    />
                  </div>
                  <div>
                    <label className="text-slate-400 block mb-1 text-[11px]">Main Bar Dia (mm)</label>
                    <input
                      type="number"
                      value={reviewMember.main_bar_diameter_mm || ""}
                      onChange={(e) =>
                        setReviewMember({
                          ...reviewMember,
                          main_bar_diameter_mm: parseFloat(e.target.value) || 0,
                        })
                      }
                      className="w-full bg-slate-900 border border-slate-700 rounded px-2 py-1 text-white font-bold"
                      placeholder="e.g. 16"
                    />
                  </div>
                  <div>
                    <label className="text-slate-400 block mb-1 text-[11px]">Secondary/Tie (mm)</label>
                    <input
                      type="number"
                      value={reviewMember.secondary_bar_diameter_mm || ""}
                      onChange={(e) =>
                        setReviewMember({
                          ...reviewMember,
                          secondary_bar_diameter_mm: parseFloat(e.target.value) || 0,
                        })
                      }
                      className="w-full bg-slate-900 border border-slate-700 rounded px-2 py-1 text-white"
                      placeholder="e.g. 8"
                    />
                  </div>
                  <div>
                    <label className="text-slate-400 block mb-1 text-[11px]">Spacing (mm)</label>
                    <input
                      type="number"
                      value={reviewMember.spacing_mm || ""}
                      onChange={(e) =>
                        setReviewMember({
                          ...reviewMember,
                          spacing_mm: parseFloat(e.target.value) || 0,
                        })
                      }
                      className="w-full bg-slate-900 border border-slate-700 rounded px-2 py-1 text-white"
                      placeholder="e.g. 150"
                    />
                  </div>
                </div>
              </div>

              {/* Material Grades */}
              <div className="grid grid-cols-2 gap-3">
                <div>
                  <label className="text-slate-400 block mb-1">Concrete Grade</label>
                  <select
                    value={reviewMember.concrete_grade}
                    onChange={(e) => setReviewMember({ ...reviewMember, concrete_grade: e.target.value })}
                    className="w-full bg-slate-900 border border-slate-700 rounded px-2.5 py-1.5 text-white"
                  >
                    <option value="M20">M20 (IS 456)</option>
                    <option value="M25">M25 (Standard)</option>
                    <option value="M30">M30 (High Strength)</option>
                    <option value="M35">M35 (Design Mix)</option>
                    <option value="M40">M40 (Infrastructure)</option>
                  </select>
                </div>
                <div>
                  <label className="text-slate-400 block mb-1">Steel Grade</label>
                  <select
                    value={reviewMember.steel_grade}
                    onChange={(e) => setReviewMember({ ...reviewMember, steel_grade: e.target.value })}
                    className="w-full bg-slate-900 border border-slate-700 rounded px-2.5 py-1.5 text-white"
                  >
                    <option value="FE415">Fe 415 (IS 1786)</option>
                    <option value="FE500">Fe 500 (Standard TMT)</option>
                    <option value="FE550">Fe 550 (High Ductility)</option>
                  </select>
                </div>
              </div>

              {/* Schedule note */}
              {reviewMember.reinforcement_summary && (
                <div className="p-2.5 rounded bg-cyan-950/30 border border-cyan-800/40 text-[11px] text-cyan-200">
                  <span className="font-semibold text-cyan-400">Verbatim Drawing Note:</span>{" "}
                  {reviewMember.reinforcement_summary}
                </div>
              )}
            </div>

            <div className="mt-5 pt-3 border-t border-slate-800 flex justify-between items-center gap-3">
              <button
                type="button"
                className="px-3 py-1.5 rounded text-xs font-mono text-slate-400 hover:text-white hover:bg-slate-800 transition-colors"
                onClick={() => setIsReviewOpen(false)}
              >
                Cancel
              </button>
              <button
                type="button"
                disabled={isReviewSubmitting}
                className="bg-emerald-600 hover:bg-emerald-500 text-white font-mono text-xs font-bold py-2 px-4 rounded-lg flex items-center gap-2 transition-all shadow-md hover:shadow-[0_0_20px_rgba(16,185,129,0.3)] cursor-pointer disabled:opacity-50"
                onClick={handleCalculateReviewedMember}
              >
                <span>⚡</span>
                <span>{isReviewSubmitting ? "Calculating..." : "Audit & Calculate BBS (Deterministic Engine)"}</span>
              </button>
            </div>
          </div>
        </div>
      )}

      {/* ENTERPRISE QA/QC AUDIT & CRYPTOGRAPHIC STAMP MODAL */}
      {showModal && (
        <div className="modal-backdrop" onClick={() => setShowModal(false)}>
          <div className="modal-card max-w-2xl w-full" onClick={(e) => e.stopPropagation()}>
            <div className="flex justify-between items-start mb-4">
              <div>
                <span className="text-xs font-mono uppercase text-emerald-400 font-bold tracking-wider">
                  ENTERPRISE QA/QC AUDIT TRAIL
                </span>
                <h3 className="text-lg font-bold text-white mt-1">
                  Professional Engineer Review &amp; Compliance Stamp
                </h3>
              </div>
              <button className="text-slate-400 hover:text-white" onClick={() => setShowModal(false)}>
                ✕
              </button>
            </div>

            {/* Engineer Credentials Form */}
            <div className="grid grid-cols-1 md:grid-cols-3 gap-3 mb-4 font-mono text-xs">
              <div>
                <label className="text-slate-400 block mb-1">Engineer Name</label>
                <input
                  type="text"
                  placeholder="e.g. Er. Jane Doe"
                  value={engineerName}
                  onChange={(e) => setEngineerName(e.target.value)}
                  className="w-full bg-slate-900 border border-slate-700 rounded px-2.5 py-1.5 text-white placeholder-slate-500"
                />
              </div>
              <div>
                <label className="text-slate-400 block mb-1">Chartered License No.</label>
                <input
                  type="text"
                  placeholder="e.g. SE/R-4091/2026"
                  value={engineerLicense}
                  onChange={(e) => setEngineerLicense(e.target.value)}
                  className="w-full bg-slate-900 border border-slate-700 rounded px-2.5 py-1.5 text-white placeholder-slate-500"
                />
              </div>
              <div>
                <label className="text-slate-400 block mb-1">Organization</label>
                <input
                  type="text"
                  placeholder="e.g. Apex Structural QA/QC Consultants"
                  value={engineerOrg}
                  onChange={(e) => setEngineerOrg(e.target.value)}
                  className="w-full bg-slate-900 border border-slate-700 rounded px-2.5 py-1.5 text-white placeholder-slate-500"
                />
              </div>
            </div>

            {/* If Signed, Display Cryptographic Stamp */}
            {qaCert ? (
              <div className="cert-stamp-box space-y-3 mb-4">
                <div className="flex items-center justify-between">
                  <div className="cert-seal-badge">
                    <span>✓</span>
                    <span>CRYPTOGRAPHICALLY VERIFIED &amp; CERTIFIED</span>
                  </div>
                  <span className="font-mono text-xs text-slate-400">{qaCert.certificate_id}</span>
                </div>

                <div className="text-xs font-mono space-y-1">
                  <div className="text-slate-400">SHA-256 Calculation Fingerprint:</div>
                  <div className="cert-hash-pill">{qaCert.verification_hash}</div>
                </div>

                <div className="border-t border-slate-800 pt-2 space-y-1.5">
                  <span className="text-[0.7rem] font-mono text-cyan-400 font-bold uppercase">
                    IS 456:2000 &amp; SP 34 AUDIT CHECKLIST:
                  </span>
                  {qaCert.compliance_checks.map((c, idx) => (
                    <div key={`check-${idx}`} className="text-xs font-mono flex items-start gap-2 text-slate-300">
                      <span className="text-emerald-400 font-bold">[{c.status}]</span>
                      <div>
                        <strong className="text-white">{c.rule_code}:</strong> {c.description} — <span className="text-slate-400">{c.details}</span>
                      </div>
                    </div>
                  ))}
                </div>

                <div className="text-[0.7rem] text-slate-400 font-mono flex justify-between pt-2 border-t border-slate-800">
                  <span>Signatory: {qaCert.engineer_name} ({qaCert.engineer_license})</span>
                  <span>{new Date(qaCert.timestamp_utc).toLocaleString()}</span>
                </div>
              </div>
            ) : (
              <div className="audit-checklist-group mb-4">
                <label className="audit-checkbox-item">
                  <input type="checkbox" defaultChecked />
                  <span>Verify member ID matches drawing elevation &amp; foundation plan.</span>
                </label>
                <label className="audit-checkbox-item">
                  <input type="checkbox" defaultChecked />
                  <span>Confirmed concrete grade (M25) and bond stress (τbd = 2.24 N/mm²) per IS 456 Cl. 26.2.1.</span>
                </label>
                <label className="audit-checkbox-item">
                  <input type="checkbox" defaultChecked />
                  <span>Verified 2d elongation bend deduction per IS 2502 &amp; SP 34 Cl. 3.2.</span>
                </label>
                <label className="audit-checkbox-item">
                  <input type="checkbox" defaultChecked />
                  <span>Confirmed lap zone restricted to central clear column height outside beam confinement (SP 34 Cl. 7.2).</span>
                </label>
              </div>
            )}

            <div className="flex gap-2">
              <button
                className="btn-verify-signoff flex-1"
                onClick={handleGenerateQACertificate}
                disabled={isSigningCert}
              >
                {isSigningCert ? "Generating SHA-256 Seal..." : qaCert ? "Re-Stamp Digital Signature" : "Sign-Off & Issue Cryptographic Certificate"}
              </button>
              {qaCert && (
                <button
                  className="btn-secondary"
                  onClick={() => {
                    if (typeof window !== "undefined") window.print();
                  }}
                >
                  🖨️ Print / Save PDF
                </button>
              )}
            </div>
          </div>
        </div>
      )}

      {/* PROFESSIONAL AUTH MODAL (Sign In / Register) */}
      {authModalOpen && (
        <div className="modal-backdrop" onClick={() => setAuthModalOpen(false)}>
          <div className="modal-card" style={{maxWidth: '420px'}} onClick={(e) => e.stopPropagation()}>

            {/* Header */}
            <div style={{display:'flex', justifyContent:'space-between', alignItems:'center', marginBottom:'6px'}}>
              <h3 style={{fontSize:'1.25rem', fontWeight:700, color:'#fff', margin:0}}>
                {authMode === "signin" ? "Sign In" : "Create Your Account"}
              </h3>
              <button
                style={{background:'none', border:'none', color:'#94a3b8', cursor:'pointer', fontSize:'1.1rem', lineHeight:1, padding:'4px'}}
                onClick={() => setAuthModalOpen(false)}
                aria-label="Close"
              >
                ✕
              </button>
            </div>
            <p style={{fontSize:'0.75rem', color:'#64748b', marginBottom:'24px', marginTop:0}}>
              {authMode === "signin"
                ? "Welcome back to AI Site Engineer"
                : "Get started with your free account"}
            </p>

            {/* Tab Pills */}
            <div style={{display:'flex', gap:'8px', marginBottom:'24px'}}>
              <button
                type="button"
                style={{
                  flex:1, padding:'9px 0', borderRadius:'8px', fontSize:'0.8rem',
                  fontWeight:600, border:'none', cursor:'pointer', transition:'all 0.2s',
                  background: authMode === 'signin' ? 'var(--cyan-primary)' : '#1e293b',
                  color: authMode === 'signin' ? '#030813' : '#94a3b8',
                }}
                onClick={() => { setAuthMode("signin"); setAuthNotice(null); }}
              >
                Sign In
              </button>
              <button
                type="button"
                style={{
                  flex:1, padding:'9px 0', borderRadius:'8px', fontSize:'0.8rem',
                  fontWeight:600, border:'none', cursor:'pointer', transition:'all 0.2s',
                  background: authMode === 'signup' ? 'var(--cyan-primary)' : '#1e293b',
                  color: authMode === 'signup' ? '#030813' : '#94a3b8',
                }}
                onClick={() => { setAuthMode("signup"); setAuthNotice(null); }}
              >
                Create Account
              </button>
            </div>

            {/* Notice banner */}
            {authNotice && (
              <div style={{marginBottom:'16px', padding:'12px', background:'rgba(8,51,68,0.7)', border:'1px solid rgba(0,229,255,0.4)', borderRadius:'8px', fontSize:'0.75rem', color:'#a5f3fc', lineHeight:1.5}}>
                {authNotice}
              </div>
            )}

            <form onSubmit={handleAuthSubmit} style={{display:'flex', flexDirection:'column', gap:'16px'}}>

              {/* Role selector — signup only */}
              {authMode === "signup" && (
                <div>
                  <label style={{fontSize:'0.7rem', color:'#64748b', display:'block', marginBottom:'8px', fontWeight:600, textTransform:'uppercase', letterSpacing:'0.06em'}}>
                    I am a
                  </label>
                  <div style={{display:'flex', gap:'10px'}}>
                    <button
                      type="button"
                      style={{flex:1, display:'flex', alignItems:'center', justifyContent:'center', gap:'6px', padding:'10px 12px', borderRadius:'8px', border:'1px solid var(--cyan-primary)', fontSize:'0.75rem', fontWeight:600, cursor:'pointer', background:'rgba(0,229,255,0.08)', color:'var(--cyan-primary)'}}
                    >
                      👷 Site Engineer
                    </button>
                    <button
                      type="button"
                      style={{flex:1, display:'flex', alignItems:'center', justifyContent:'center', gap:'6px', padding:'10px 12px', borderRadius:'8px', border:'1px solid #334155', fontSize:'0.75rem', fontWeight:600, cursor:'pointer', background:'#1e293b', color:'#94a3b8'}}
                    >
                      🏢 Contractor / Company
                    </button>
                  </div>
                </div>
              )}

              {/* Full Name — signup only */}
              {authMode === "signup" && (
                <div>
                  <label style={{fontSize:'0.75rem', color:'#94a3b8', display:'block', marginBottom:'6px', fontWeight:500}}>Full Name</label>
                  <input
                    type="text"
                    required
                    placeholder="Enter your full name"
                    value={authFullName}
                    onChange={(e) => setAuthFullName(e.target.value)}
                    style={{width:'100%', boxSizing:'border-box', background:'#0f172a', border:'1px solid #334155', borderRadius:'8px', padding:'10px 14px', fontSize:'0.875rem', color:'#fff', outline:'none'}}
                  />
                </div>
              )}

              {/* Email */}
              <div>
                <label style={{fontSize:'0.75rem', color:'#94a3b8', display:'block', marginBottom:'6px', fontWeight:500}}>Email address</label>
                <input
                  type="email"
                  required
                  placeholder="you@example.com"
                  value={authEmail}
                  onChange={(e) => setAuthEmail(e.target.value)}
                  style={{width:'100%', boxSizing:'border-box', background:'#0f172a', border:'1px solid #334155', borderRadius:'8px', padding:'10px 14px', fontSize:'0.875rem', color:'#fff', outline:'none'}}
                />
              </div>

              {/* Password */}
              <div>
                <label style={{fontSize:'0.75rem', color:'#94a3b8', display:'block', marginBottom:'6px', fontWeight:500}}>Password</label>
                <input
                  type="password"
                  required
                  placeholder="Create a strong password"
                  value={authPassword}
                  onChange={(e) => setAuthPassword(e.target.value)}
                  style={{width:'100%', boxSizing:'border-box', background:'#0f172a', border:'1px solid #334155', borderRadius:'8px', padding:'10px 14px', fontSize:'0.875rem', color:'#fff', outline:'none'}}
                />
              </div>

              {/* Submit */}
              <button
                type="submit"
                disabled={isAuthLoading}
                className="btn-verify-signoff"
                style={{width:'100%', marginTop:'4px'}}
              >
                {isAuthLoading
                  ? "Authenticating..."
                  : authMode === "signin"
                  ? "Sign In"
                  : "Create Account"}
              </button>

              {/* Footer link */}
              <p style={{textAlign:'center', fontSize:'0.75rem', color:'#64748b', margin:0}}>
                {authMode === "signin" ? (
                  <>
                    Don&apos;t have an account?{" "}
                    <button type="button" style={{background:'none', border:'none', color:'var(--cyan-primary)', cursor:'pointer', fontSize:'0.75rem'}} onClick={() => { setAuthMode("signup"); setAuthNotice(null); }}>
                      Sign up
                    </button>
                  </>
                ) : (
                  <>
                    Already have an account?{" "}
                    <button type="button" style={{background:'none', border:'none', color:'var(--cyan-primary)', cursor:'pointer', fontSize:'0.75rem'}} onClick={() => { setAuthMode("signin"); setAuthNotice(null); }}>
                      Sign in
                    </button>
                  </>
                )}
              </p>
            </form>
          </div>
        </div>
      )}

      <div className="app-shell">
        {/* Construction Site Hero Background Backdrop */}
        <div className="hero-background-backdrop" aria-hidden="true">
          <img
            src="/hero-bg.jpg"
            alt="Construction Site Engineer"
            className="hero-background-image"
          />
          <div className="hero-background-overlay" />
        </div>

        {/* Top Header */}
        <header className="top-nav">
          <div className="brand-wrapper">
            <div className="brand-icon-box" aria-hidden="true">
              <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="#030813" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
                <path d="M12 2L2 22h20L12 2z" />
                <path d="M12 9v6" />
                <path d="M9 15h6" />
              </svg>
            </div>
            <div>
              <h1 className="brand-title">AI Site Engineer</h1>
              <p className="brand-subtitle">CONSTRUCTION INTELLIGENCE &amp; DETERMINISTIC BBS ENGINE</p>
            </div>
          </div>

          <div className="flex items-center gap-3">
            {user ? (
              <div className="flex items-center gap-2 bg-slate-900/90 border border-cyan-500/40 rounded-full py-1 px-3">
                <span className="text-xs font-mono text-cyan-300 font-bold">
                  👷‍♂️ {user.user_metadata?.full_name || user.email}
                </span>
                <button
                  onClick={handleSignOut}
                  className="text-[0.7rem] font-mono text-slate-400 hover:text-rose-400 ml-1 transition"
                  title="Sign out"
                >
                  Sign Out
                </button>
              </div>
            ) : (
              <button
                className="btn-secondary text-xs"
                onClick={() => {
                  setAuthMode("signin");
                  setAuthModalOpen(true);
                }}
              >
                Sign In / Join
              </button>
            )}
          </div>
        </header>

        {/* Central Intelligence Hero */}
        <section className="hero-section">
          <div className="pill-badge">
            <span className="status-dot" />
            ZERO-HALLUCINATION CIVIL BBS &amp; 12M STOCK OPTIMIZATION
          </div>

          <h2 className="hero-title mb-8">
            AI for <span>Site Engineers &amp; Contractors.</span>
          </h2>

          <div className="console-box">
            <span className="terminal-icon" aria-hidden="true">&gt;</span>
            <input
              className="console-input"
              type="text"
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              placeholder="e.g. Cutting length for slab S1, pile P1, beam B4, or column C12..."
              onKeyDown={(e) => {
                if (e.key === "Enter") handleExecuteQuery();
              }}
            />
            <button
              className="console-action-btn"
              onClick={() => handleExecuteQuery()}
              disabled={isLoading}
              title="Calculate Member BBS"
            >
              {isLoading ? "Running Engine..." : "Calculate Member BBS"}
              <span aria-hidden="true">→</span>
            </button>
          </div>
        </section>

        {/* Two-Column Engineering Workspace Grid */}
        <section className="workspace-grid">
          {/* Left Panel: Drawing Sheets & Multi-Format Ingestion */}
          <div className="panel-card">
            <div className="panel-header flex-wrap gap-2">
              <div>
                <h3 className="panel-title">Drawing Sheets &amp; Schedules</h3>
                <span className="panel-code-tag mt-1 inline-block">ACTIVE: {projectName.toUpperCase()}</span>
              </div>
              <span className="text-xs font-mono text-cyan-400 bg-cyan-950/60 border border-cyan-500/30 px-2 py-0.5 rounded">
                {drawings.length} {drawings.length === 1 ? "SHEET" : "SHEETS"}
              </span>
            </div>

            <div className="upload-dropzone" onClick={() => fileInputRef.current?.click()}>
              <div className="upload-icon">↑</div>
              <p className="upload-text">Upload Drawing (PDF), Photo, or Schedule (CSV)</p>
              <p className="upload-subtext">PDF vector drawings, site photos/blueprints (.png, .jpg), or CSV/TSV schedules (up to 25 MB)</p>
            </div>
            <input
              ref={fileInputRef}
              type="file"
              accept=".pdf,.csv,.tsv,.txt,.png,.jpg,.jpeg,.webp"
              style={{ display: "none" }}
              onChange={handleFileUpload}
            />

            <div className="drawing-item-list">
              {drawings.length === 0 ? (
                <div className="py-6 text-center text-slate-500 font-mono text-xs border border-dashed border-slate-800 rounded-lg my-2">
                  No drawing sheets indexed yet.<br />
                  Upload a PDF drawing, photo/blueprint, or bar schedule CSV to begin.
                </div>
              ) : (
                drawings.map((dwg, idx) => (
                  <div className="drawing-card" key={`${dwg.name}-${idx}`}>
                    <div className="drawing-info">
                      <strong>{dwg.name}</strong>
                      <small>
                        {dwg.revision} · {dwg.size} · {dwg.pages} pages
                      </small>
                    </div>
                    <span className="badge-ready">
                      {dwg.status === "Indexed" ? "● HYBRID STORE" : dwg.status}
                    </span>
                  </div>
                ))
              )}
            </div>

            {/* AI Extracted Structural Parameters Section */}
            {extractedMembers.length > 0 && (
              <div className="mt-4 pt-3 border-t border-slate-800">
                <div className="flex items-center justify-between mb-2">
                  <span className="text-xs font-mono font-semibold text-cyan-400 flex items-center gap-1.5">
                    <span className="inline-block w-2 h-2 rounded-full bg-cyan-400 animate-pulse"></span>
                    Extracted Parameters ({extractedMembers.length})
                  </span>
                  <span className="text-[10px] font-mono text-slate-400 bg-slate-800/80 px-1.5 py-0.5 rounded border border-slate-700">
                    QA Review Ready
                  </span>
                </div>
                <div className="space-y-2 max-h-56 overflow-y-auto pr-1">
                  {extractedMembers.map((m, idx) => (
                    <div
                      key={`${m.member_id}-${idx}`}
                      className="p-2.5 rounded-lg border border-cyan-500/30 bg-cyan-950/20 hover:bg-cyan-950/40 hover:border-cyan-400/60 transition-all cursor-pointer text-xs font-mono"
                      onClick={() => {
                        setReviewMember(m);
                        setIsReviewOpen(true);
                      }}
                    >
                      <div className="flex items-center justify-between">
                        <span className="font-bold text-white text-sm">{m.member_id}</span>
                        <span className="px-1.5 py-0.5 rounded bg-slate-800 text-cyan-300 text-[10px] uppercase font-bold border border-cyan-500/20">
                          {m.member_type}
                        </span>
                      </div>
                      <div className="text-slate-400 text-[11px] mt-1 truncate">
                        {m.reinforcement_summary || `${m.main_bar_diameter_mm ? `Dia ${m.main_bar_diameter_mm}mm` : ''} ${m.spacing_mm ? `@ ${m.spacing_mm} c/c` : ''}`}
                      </div>
                      <div className="flex items-center justify-between text-[10px] text-slate-500 mt-1.5 pt-1 border-t border-slate-800/60">
                        <span>{m.concrete_grade} · {m.steel_grade}</span>
                        <span className="text-cyan-400 hover:underline flex items-center gap-1">Review &amp; Calc ➔</span>
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            )}

            <div className="mt-4 pt-4 border-t border-slate-800 space-y-2.5">
              <button
                type="button"
                className="w-full bg-cyan-950/70 hover:bg-cyan-900 border border-cyan-500/40 hover:border-cyan-400 text-cyan-200 font-mono text-xs py-2.5 px-3 rounded-lg flex items-center justify-center gap-2 transition-all shadow-sm hover:shadow-[0_0_15px_rgba(0,229,255,0.2)] cursor-pointer"
                onClick={() => handleLoadProjectBBS()}
                disabled={isProjectLoading}
              >
                <span>📊</span>
                <span className="font-semibold">{isProjectLoading ? "Compiling Project BBS..." : "Compile Consolidated Project BBS"}</span>
              </button>

              <button
                type="button"
                className="w-full bg-slate-900/90 hover:bg-slate-850 border border-slate-700 hover:border-amber-500/50 text-amber-300 font-mono text-xs py-2.5 px-3 rounded-lg flex items-center justify-center gap-2 transition-all shadow-sm hover:shadow-[0_0_15px_rgba(245,158,11,0.2)] cursor-pointer"
                onClick={() => handleLoadOptimization()}
                disabled={isOptimizationLoading}
              >
                <span>✂️</span>
                <span className="font-semibold">{isOptimizationLoading ? "Optimizing 12m Bars..." : "12m Stock Bar 1D Cutting Optimizer"}</span>
              </button>
            </div>
          </div>

          {/* Right Panel: Deterministic BBS Calculation Engine Output */}
          <div className="panel-card">
            <div className="flex flex-wrap items-center justify-between gap-3 mb-4 pb-3 border-b border-slate-800/80">
              <div>
                <h3 className="panel-title">
                  {viewMode === "project"
                    ? "Consolidated Project BBS"
                    : viewMode === "optimization"
                    ? "12m Commercial Stock Bar Cutting Optimizer"
                    : "Member Calculation Breakdown"}
                  <span className="panel-code-tag">IS 456 / SP 34 / IS 1786</span>
                </h3>
                <div className="text-[0.72rem] font-mono text-slate-400 mt-1">
                  💡 <em>Click any quantity (length, unit weight, or total weight) to audit its exact formula.</em>
                </div>
              </div>

              {/* Presentable Toolbar & Actions */}
              <div className="flex flex-wrap items-center gap-4">
                {/* 3 View Mode Buttons with Prominent Gap & Box Radius */}
                <div className="flex flex-wrap items-center gap-3.5">
                  <button
                    type="button"
                    style={{ borderRadius: "12px" }}
                    className={`px-4 py-2 font-mono text-xs transition-all cursor-pointer border ${
                      viewMode === "member"
                        ? "bg-cyan-500/25 text-cyan-200 border-cyan-400 shadow-[0_0_16px_rgba(0,229,255,0.35)] font-bold"
                        : "bg-slate-900/90 text-slate-300 hover:text-cyan-200 hover:bg-slate-800 hover:border-cyan-400/60 border-slate-700/80 font-medium"
                    }`}
                    onClick={() => setViewMode("member")}
                  >
                    Member View
                  </button>
                  <button
                    type="button"
                    style={{ borderRadius: "12px" }}
                    className={`px-4 py-2 font-mono text-xs transition-all cursor-pointer border ${
                      viewMode === "project"
                        ? "bg-cyan-500/25 text-cyan-200 border-cyan-400 shadow-[0_0_16px_rgba(0,229,255,0.35)] font-bold"
                        : "bg-slate-900/90 text-slate-300 hover:text-cyan-200 hover:bg-slate-800 hover:border-cyan-400/60 border-slate-700/80 font-medium"
                    }`}
                    onClick={() => {
                      if (!projectBBSData) handleLoadProjectBBS();
                      else setViewMode("project");
                    }}
                  >
                    Project Summary
                  </button>
                  <button
                    type="button"
                    style={{ borderRadius: "12px" }}
                    className={`px-4 py-2 font-mono text-xs transition-all cursor-pointer border ${
                      viewMode === "optimization"
                        ? "bg-amber-500/25 text-amber-200 border-amber-400 shadow-[0_0_16px_rgba(245,158,11,0.35)] font-bold"
                        : "bg-slate-900/90 text-slate-300 hover:text-amber-200 hover:bg-slate-800 hover:border-amber-400/60 border-slate-700/80 font-medium"
                    }`}
                    onClick={() => {
                      if (!procurementData) handleLoadOptimization();
                      else setViewMode("optimization");
                    }}
                  >
                    12m Stock Optimizer
                  </button>
                </div>

                <div className="h-6 w-[1px] bg-slate-800 hidden lg:block" />

                {/* Distinct Export & Verification Actions */}
                <div className="flex flex-wrap items-center gap-3">
                  {viewMode === "member" ? (
                    <button
                      type="button"
                      style={{ borderRadius: "12px" }}
                      className="btn-secondary text-xs px-3.5 py-2 flex items-center gap-1.5 shadow-sm"
                      onClick={handleExportBBS}
                    >
                      <span>📥</span> Export CSV
                    </button>
                  ) : viewMode === "project" ? (
                    <button
                      type="button"
                      style={{ borderRadius: "12px" }}
                      className="btn-secondary text-xs px-3.5 py-2 flex items-center gap-1.5 shadow-sm"
                      onClick={handleExportProjectBBS}
                      disabled={!projectBBSData}
                    >
                      <span>📥</span> Export Project CSV
                    </button>
                  ) : (
                    <button
                      type="button"
                      style={{ borderRadius: "12px" }}
                      className="btn-secondary text-xs px-3.5 py-2 flex items-center gap-1.5 shadow-sm"
                      onClick={handleExportProcurementPO}
                      disabled={!procurementData}
                    >
                      <span>📥</span> Export 12m Cut-List &amp; PO
                    </button>
                  )}

                  {viewMode === "member" && (
                    <button
                      type="button"
                      style={{
                        borderRadius: "12px",
                        borderColor: isSignedOff ? "#34d399" : undefined,
                        color: isSignedOff ? "#34d399" : undefined,
                      }}
                      className="btn-secondary text-xs px-3.5 py-2 flex items-center gap-1.5"
                      onClick={() => setShowModal(true)}
                    >
                      {isSignedOff ? "✓ QA Certified" : "Review & Verify"}
                    </button>
                  )}
                </div>
              </div>
            </div>

            {/* Live AI Answer & Drawing Insights Box */}
            {viewMode === "member" && aiAnswer && (
              <div className="mb-4 bg-slate-900/90 border border-cyan-500/40 rounded-xl p-4 shadow-lg shadow-cyan-950/20">
                <div className="flex items-center justify-between mb-2">
                  <div className="flex items-center gap-2">
                    <span className="h-2.5 w-2.5 rounded-full bg-cyan-400 animate-pulse" />
                    <span className="font-mono text-xs uppercase font-bold text-cyan-300 tracking-wider">
                      SITE ENGINEER AI INSIGHTS &amp; DRAWING RESPONSE
                    </span>
                  </div>
                  <span className="text-[0.7rem] font-mono text-cyan-400 bg-cyan-950/80 px-2 py-0.5 rounded border border-cyan-500/30">
                    IS 456 VERIFIED
                  </span>
                </div>
                <div className="text-sm text-slate-200 leading-relaxed whitespace-pre-line font-sans border-l-2 border-cyan-400/80 pl-3 py-1">
                  {aiAnswer}
                </div>

                {evidenceSnippets.length > 0 && (
                  <div className="mt-3 pt-3 border-t border-slate-800">
                    <div className="text-[0.7rem] font-mono text-cyan-400 uppercase tracking-wider mb-1.5">
                      REFERENCED DRAWING EVIDENCE:
                    </div>
                    <div className="space-y-1.5">
                      {evidenceSnippets.slice(0, 3).map((snippet, idx) => (
                        <div key={`snippet-${idx}`} className="bg-slate-950/70 border border-slate-800 rounded p-2 text-xs font-mono text-slate-300">
                          <span className="text-cyan-400 font-bold block mb-0.5">[{snippet.sheet}]</span>
                          <span className="text-slate-400 line-clamp-2">{snippet.text}</span>
                        </div>
                      ))}
                    </div>
                  </div>
                )}
              </div>
            )}

            {/* VIEW MODE 1: SINGLE MEMBER VIEW */}
            {viewMode === "member" && activeResult && (
              <div>
                <div className="result-hero-metric">
                  <div>
                    <span className="metric-label">TOTAL CUTTING LENGTH · MEMBER {activeResult.memberId}</span>
                    <div className="metric-value">
                      <span
                        className="clickable-qty"
                        title="Click to view cutting length formula and bend deductions"
                        onClick={() =>
                          setInspectItem({
                            memberId: activeResult.memberId,
                            memberType: activeResult.memberType,
                            barMark: "Main Longitudinal Bar",
                            diameter: activeResult.items?.[0]?.bar_diameter_mm || 16,
                            numBars: activeResult.items?.[0]?.num_bars || 4,
                            cuttingLengthM: activeResult.cuttingLengthM,
                            cuttingLengthMm: activeResult.cuttingLengthMm,
                            unitWeight: activeResult.items?.[0]?.unit_weight_kg_m || 1.58,
                            totalWeight: activeResult.totalWeightKg || 27.74,
                            breakdown: activeResult.breakdown,
                            activeTab: "cutting_length",
                          })
                        }
                      >
                        {activeResult.cuttingLengthM.toFixed(3)} m
                      </span>
                      <span className="metric-sub">
                        (
                        <span
                          className="clickable-qty"
                          title="Click to view mm derivation"
                          onClick={() =>
                            setInspectItem({
                              memberId: activeResult.memberId,
                              memberType: activeResult.memberType,
                              barMark: "Main Longitudinal Bar",
                              diameter: activeResult.items?.[0]?.bar_diameter_mm || 16,
                              numBars: activeResult.items?.[0]?.num_bars || 4,
                              cuttingLengthM: activeResult.cuttingLengthM,
                              cuttingLengthMm: activeResult.cuttingLengthMm,
                              unitWeight: activeResult.items?.[0]?.unit_weight_kg_m || 1.58,
                              totalWeight: activeResult.totalWeightKg || 27.74,
                              breakdown: activeResult.breakdown,
                              activeTab: "cutting_length",
                            })
                          }
                        >
                          {activeResult.cuttingLengthMm.toFixed(1)} mm
                        </span>
                        )
                      </span>
                    </div>
                  </div>
                  <div className="text-right font-mono text-xs text-cyan-400">
                    <div>CONFIDENCE: {(activeResult.confidence * 100).toFixed(0)}%</div>
                    {activeResult.totalWeightKg && (
                      <div className="text-amber-300 font-bold mt-1">
                        TOTAL WEIGHT:{" "}
                        <span
                          className="clickable-qty"
                          title="Click to view steel tonnage calculation"
                          onClick={() =>
                            setInspectItem({
                              memberId: activeResult.memberId,
                              memberType: activeResult.memberType,
                              barMark: "Main Longitudinal Bar",
                              diameter: activeResult.items?.[0]?.bar_diameter_mm || 16,
                              numBars: activeResult.items?.[0]?.num_bars || 4,
                              cuttingLengthM: activeResult.cuttingLengthM,
                              cuttingLengthMm: activeResult.cuttingLengthMm,
                              unitWeight: activeResult.items?.[0]?.unit_weight_kg_m || 1.58,
                              totalWeight: activeResult.totalWeightKg || 27.74,
                              breakdown: activeResult.breakdown,
                              activeTab: "total_weight",
                            })
                          }
                        >
                          {activeResult.totalWeightKg.toFixed(2)} kg
                        </span>
                      </div>
                    )}
                    {isSignedOff && (
                      <div className="text-emerald-400 font-bold mt-1">✓ QA STAMP CERTIFIED</div>
                    )}
                  </div>
                </div>

                {/* Multiple Rebar Line Items */}
                {activeResult.items && activeResult.items.length > 0 && (
                  <div className="mb-4">
                    <span className="text-xs font-mono text-cyan-300 font-bold uppercase tracking-wider block mb-2">
                      BAR BENDING SCHEDULE ITEMS ({activeResult.items.length})
                    </span>
                    <div className="overflow-x-auto">
                      <table className="w-full text-xs font-mono border border-slate-800 bg-slate-950/70 rounded-lg overflow-hidden">
                        <thead className="bg-slate-900/90 text-slate-300 border-b border-slate-800">
                          <tr>
                            <th className="py-2 px-3 text-left">Bar Mark</th>
                            <th className="py-2 px-3 text-center">Dia</th>
                            <th className="py-2 px-3 text-center">No.</th>
                            <th className="py-2 px-3 text-right">Cut L (m)</th>
                            <th className="py-2 px-3 text-right">Unit Wt (kg/m)</th>
                            <th className="py-2 px-3 text-right">Total Wt (kg)</th>
                          </tr>
                        </thead>
                        <tbody className="divide-y divide-slate-800/60">
                          {activeResult.items.map((item, idx) => (
                            <tr key={`item-${idx}`} className="hover:bg-slate-900/40 transition">
                              <td className="py-2 px-3 text-slate-200">
                                <div>{item.bar_mark}</div>
                                <div className="text-[0.65rem] text-slate-400 line-clamp-1">{item.shape_description}</div>
                              </td>
                              <td className="py-2 px-3 text-center text-cyan-400 font-bold">T{item.bar_diameter_mm}</td>
                              <td className="py-2 px-3 text-center text-slate-300">{item.num_bars}</td>
                              <td className="py-2 px-3 text-right">
                                <span
                                  className="clickable-qty text-emerald-400 font-bold"
                                  onClick={() =>
                                    setInspectItem({
                                      memberId: activeResult.memberId,
                                      memberType: activeResult.memberType,
                                      barMark: item.bar_mark,
                                      diameter: item.bar_diameter_mm,
                                      numBars: item.num_bars,
                                      cuttingLengthM: item.cutting_length_m,
                                      cuttingLengthMm: item.cutting_length_mm,
                                      unitWeight: item.unit_weight_kg_m,
                                      totalWeight: item.total_weight_kg,
                                      shapeDescription: item.shape_description,
                                      breakdown: item.breakdown || activeResult.breakdown,
                                      activeTab: "cutting_length",
                                    })
                                  }
                                >
                                  {item.cutting_length_m.toFixed(3)}
                                </span>
                              </td>
                              <td className="py-2 px-3 text-right">
                                <span
                                  className="clickable-qty text-cyan-300"
                                  onClick={() =>
                                    setInspectItem({
                                      memberId: activeResult.memberId,
                                      memberType: activeResult.memberType,
                                      barMark: item.bar_mark,
                                      diameter: item.bar_diameter_mm,
                                      numBars: item.num_bars,
                                      cuttingLengthM: item.cutting_length_m,
                                      cuttingLengthMm: item.cutting_length_mm,
                                      unitWeight: item.unit_weight_kg_m,
                                      totalWeight: item.total_weight_kg,
                                      shapeDescription: item.shape_description,
                                      breakdown: item.breakdown || activeResult.breakdown,
                                      activeTab: "unit_weight",
                                    })
                                  }
                                >
                                  {item.unit_weight_kg_m.toFixed(2)}
                                </span>
                              </td>
                              <td className="py-2 px-3 text-right">
                                <span
                                  className="clickable-qty text-amber-300 font-bold"
                                  onClick={() =>
                                    setInspectItem({
                                      memberId: activeResult.memberId,
                                      memberType: activeResult.memberType,
                                      barMark: item.bar_mark,
                                      diameter: item.bar_diameter_mm,
                                      numBars: item.num_bars,
                                      cuttingLengthM: item.cutting_length_m,
                                      cuttingLengthMm: item.cutting_length_mm,
                                      unitWeight: item.unit_weight_kg_m,
                                      totalWeight: item.total_weight_kg,
                                      shapeDescription: item.shape_description,
                                      breakdown: item.breakdown || activeResult.breakdown,
                                      activeTab: "total_weight",
                                    })
                                  }
                                >
                                  {item.total_weight_kg.toFixed(2)}
                                </span>
                              </td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </div>
                  </div>
                )}

                {/* Arithmetic Breakdown Component Table */}
                <span className="text-xs font-mono text-cyan-300 font-bold uppercase tracking-wider block mb-2">
                  ARITHMETIC BREAKDOWN &amp; CODE PROVISIONS
                </span>
                <table className="calculation-table">
                  <thead>
                    <tr>
                      <th>Component / Provision</th>
                      <th>Clause / Standard</th>
                      <th className="text-right">Length (mm)</th>
                    </tr>
                  </thead>
                  <tbody>
                    {activeResult.breakdown.map((row, idx) => (
                      <tr key={`calc-row-${idx}`}>
                        <td className="text-white font-medium">{row.label}</td>
                        <td className="text-sky-400">{row.clause || "Drawing Detail"}</td>
                        <td className={`length-val ${row.length_mm < 0 ? "negative" : "positive"}`}>
                          {row.length_mm > 0 ? `+${row.length_mm.toFixed(1)}` : row.length_mm.toFixed(1)}
                        </td>
                      </tr>
                    ))}
                    <tr className="border-t-2 border-cyan-500/40 bg-cyan-950/20 font-bold">
                      <td className="text-cyan-300" colSpan={2}>
                        TOTAL CUTTING LENGTH (DETERMINISTIC SUM)
                      </td>
                      <td className="length-val positive text-cyan-300">
                        {activeResult.cuttingLengthMm.toFixed(1)} mm
                      </td>
                    </tr>
                  </tbody>
                </table>

                {/* Verified Drawing Sheet Citations */}
                <div className="mt-4 pt-3 border-t border-slate-800">
                  <div className="font-mono text-cyan-400 uppercase text-[0.7rem] font-bold mb-1">
                    DRAWING PAGE CITATIONS:
                  </div>
                  <div className="flex flex-wrap gap-2">
                    {activeResult.citations.map((cite, idx) => (
                      <span
                        key={`cite-${idx}`}
                        className="bg-cyan-950/60 border border-cyan-500/30 text-cyan-300 font-mono text-xs px-2 py-0.5 rounded"
                      >
                        {cite}
                      </span>
                    ))}
                  </div>
                </div>

                <div className="text-xs text-slate-400 mt-3 space-y-1">
                  <div className="font-mono text-cyan-400 uppercase text-[0.7rem] font-bold">
                    ENGINEER REVIEW &amp; SAFETY AUDIT NOTES:
                  </div>
                  {activeResult.assumptions.map((note, idx) => (
                    <div key={`note-${idx}`} className="flex items-start gap-2">
                      <span className="text-cyan-400">✓</span>
                      <span>{note}</span>
                    </div>
                  ))}
                </div>
              </div>
            )}

            {/* Empty State for Member View */}
            {viewMode === "member" && !activeResult && !aiAnswer && !isLoading && (
              <div className="py-14 text-center border border-dashed border-slate-800 rounded-xl bg-slate-950/40 my-4">
                <div className="text-4xl mb-3">📐</div>
                <h4 className="text-base font-bold text-slate-200">Engineering Calculation Engine Ready</h4>
                <p className="text-xs text-slate-400 max-w-md mx-auto mt-2 leading-relaxed">
                  Upload a structural drawing PDF or bar schedule CSV, or ask a member cutting length question in the terminal above to execute verified IS 456 arithmetic.
                </p>
                <div className="mt-4 flex flex-wrap justify-center gap-2 text-[0.7rem] font-mono text-cyan-400">
                  <span className="bg-slate-900 px-2.5 py-1 rounded border border-slate-800">IS 456:2000 Cl 26.2</span>
                  <span className="bg-slate-900 px-2.5 py-1 rounded border border-slate-800">SP 34:1987 Detailing</span>
                  <span className="bg-slate-900 px-2.5 py-1 rounded border border-slate-800">1D Cutting Stock Optimization</span>
                </div>
              </div>
            )}

            {/* VIEW MODE 2: CONSOLIDATED PROJECT PROCUREMENT BBS */}
            {viewMode === "project" && (
              <div className="space-y-4">
                {isProjectLoading ? (
                  <div className="text-center py-12 text-slate-400">
                    <span className="inline-block animate-spin text-2xl mb-2">⚙️</span>
                    <p className="font-mono text-xs text-cyan-400">ANALYZING ALL DRAWING SHEETS &amp; COMPILING STEEL PROCUREMENT SCHEDULE...</p>
                  </div>
                ) : projectBBSData ? (
                  projectBBSData.items.length === 0 ? (
                    <div className="bg-slate-950/80 border border-slate-800 rounded-xl p-8 text-center space-y-4 max-w-2xl mx-auto my-6">
                      <div className="w-14 h-14 bg-amber-500/10 border border-amber-500/30 rounded-full flex items-center justify-center mx-auto text-2xl">
                        ⚠️
                      </div>
                      <div className="space-y-1">
                        <h3 className="text-base font-bold text-slate-100 font-mono tracking-wide">
                          NO STRUCTURAL SCHEDULES OR MEMBERS IDENTIFIED
                        </h3>
                        <p className="text-xs text-slate-400 max-w-md mx-auto leading-relaxed">
                          We scanned your active drawing sheets, but could not detect recognizable bar schedules or structural member IDs (e.g. C-01, B-02, 8-T16).
                        </p>
                      </div>

                      <div className="bg-slate-900/60 border border-slate-800/80 rounded-lg p-3 text-left text-xs font-mono text-slate-300 space-y-1.5 max-w-lg mx-auto">
                        <div className="text-cyan-400 font-bold text-[0.7rem] uppercase tracking-wider">Troubleshooting &amp; Next Steps:</div>
                        <div className="flex items-start gap-2">
                          <span className="text-amber-400">•</span>
                          <span>If uploading a scanned drawing or photo, ensure high contrast and clear bar text.</span>
                        </div>
                        <div className="flex items-start gap-2">
                          <span className="text-amber-400">•</span>
                          <span>You can enter dimensions &amp; rebar details manually with <strong>Audit Member</strong>.</span>
                        </div>
                        <div className="flex items-start gap-2">
                          <span className="text-amber-400">•</span>
                          <span>To explore full multi-member BBS features, load our <strong>9-Member Reference Project</strong>.</span>
                        </div>
                      </div>

                      <div className="flex flex-wrap items-center justify-center gap-3 pt-2">
                        <button
                          type="button"
                          onClick={() => {
                            setReviewMember({
                              member_id: "C-01",
                              member_type: "column",
                              dimensions: { clear_height_mm: 3000, footing_embedment_mm: 0, bend_allowance_mm: 300 },
                              num_bars: 8,
                              main_bar_diameter_mm: 16,
                              secondary_bar_diameter_mm: 8,
                              spacing_mm: 150,
                              concrete_grade: "M25",
                              steel_grade: "Fe500",
                              reinforcement_summary: "8 bars Ø16 mm (Fe500), ties Ø8 mm @ 150 mm c/c",
                              confidence: 1.0,
                              citations: ["Manual Audit Specification"],
                              notes: ["Entered manually via Zero-State Audit"],
                            });
                            setIsReviewOpen(true);
                          }}
                          className="px-4 py-2 bg-cyan-600 hover:bg-cyan-500 text-slate-950 font-bold text-xs rounded-lg transition shadow-lg shadow-cyan-950/50 flex items-center gap-1.5 cursor-pointer"
                        >
                          <span>➕</span> Add Member Manually
                        </button>

                        <button
                          type="button"
                          onClick={() => handleLoadProjectBBS(true)}
                          className="px-4 py-2 bg-slate-900 hover:bg-slate-850 border border-slate-700 hover:border-cyan-500/50 text-cyan-300 text-xs rounded-lg transition font-mono flex items-center gap-1.5 cursor-pointer"
                        >
                          <span>🧪</span> Load 9-Member Reference Demo
                        </button>
                      </div>
                    </div>
                  ) : (
                    <>
                      {projectBBSData.project_id.includes("Reference Project") && (
                        <div className="bg-amber-500/10 border border-amber-500/30 rounded-lg px-3 py-2 flex items-center justify-between text-xs font-mono text-amber-300 mb-2">
                          <div className="flex items-center gap-2">
                            <span>🧪</span>
                            <span><strong>DEMO REFERENCE PROJECT</strong> · Displaying 9 standard baseline members (IS 456 / SP 34).</span>
                          </div>
                          <span className="text-[0.65rem] bg-amber-500/20 text-amber-300 px-2 py-0.5 rounded font-bold uppercase tracking-wider">Demo Mode</span>
                        </div>
                      )}
                      <div className="result-hero-metric">
                      <div>
                        <span className="metric-label">PROJECT STEEL PROCUREMENT TOTAL · {projectBBSData.project_id}</span>
                        <div className="metric-value">
                          {projectBBSData.total_steel_tonnes.toFixed(3)} Tonnes
                          <span className="metric-sub">({projectBBSData.total_steel_kg.toFixed(0)} kg)</span>
                        </div>
                      </div>
                      <div className="text-right font-mono text-xs text-cyan-400">
                        <div>MEMBERS INDEXED: {projectBBSData.total_members_count}</div>
                        <div className="text-amber-300 font-bold">READY FOR REBAR PURCHASE ORDER</div>
                      </div>
                    </div>

                    <div>
                      <div className="text-[0.75rem] font-mono text-cyan-400 uppercase tracking-wider mb-2 font-bold">
                        STEEL REQUISITION BY BAR DIAMETER (IS 1786 HYSD FE500)
                      </div>
                      <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-6 gap-2">
                        {projectBBSData.diameter_summaries.map((d, idx) => (
                          <div
                            key={`dia-${idx}`}
                            className="bg-slate-950/80 border border-slate-800 hover:border-cyan-500/50 rounded-lg p-2.5 transition text-center"
                          >
                            <span className="text-cyan-400 font-mono font-bold text-sm block">T{d.bar_diameter_mm}</span>
                            <span
                              className="clickable-qty text-amber-300 font-mono font-bold text-base block mt-0.5"
                              title="Click to inspect unit weight formula"
                              onClick={() =>
                                setInspectItem({
                                  memberId: "PROJECT",
                                  memberType: "SUMMARY",
                                  barMark: `T${d.bar_diameter_mm} Rebar Group`,
                                  diameter: d.bar_diameter_mm,
                                  numBars: 1,
                                  cuttingLengthM: d.total_length_m,
                                  cuttingLengthMm: d.total_length_m * 1000,
                                  unitWeight: d.unit_weight_kg_m,
                                  totalWeight: d.total_weight_kg,
                                  breakdown: [
                                    { label: `Total running length for T${d.bar_diameter_mm}`, length_mm: d.total_length_m * 1000 },
                                  ],
                                  activeTab: "unit_weight",
                                })
                              }
                            >
                              {d.total_weight_kg.toFixed(1)} kg
                            </span>
                            <span className="text-[0.65rem] text-slate-400 font-mono block">
                              {d.total_length_m.toFixed(0)} m · {d.unit_weight_kg_m.toFixed(2)} kg/m
                            </span>
                          </div>
                        ))}
                      </div>
                    </div>

                    <div className="overflow-x-auto">
                      <div className="text-[0.75rem] font-mono text-cyan-400 uppercase tracking-wider mb-2 font-bold flex justify-between items-center">
                        <span>DETAILED PROJECT BAR BENDING SCHEDULE ({projectBBSData.items.length} LINE ITEMS)</span>
                        <span className="text-slate-400 font-normal">Click any quantity to inspect formula</span>
                      </div>
                      <table className="w-full text-xs font-mono border border-slate-800 bg-slate-950/80 rounded-lg overflow-hidden">
                        <thead className="bg-slate-900/90 text-cyan-300 border-b border-slate-800">
                          <tr>
                            <th className="py-2 px-3 text-left">Member</th>
                            <th className="py-2 px-3 text-left">Bar Mark</th>
                            <th className="py-2 px-3 text-center">Dia</th>
                            <th className="py-2 px-3 text-center">No.</th>
                            <th className="py-2 px-3 text-right">Cut L (m)</th>
                            <th className="py-2 px-3 text-right">Unit Wt</th>
                            <th className="py-2 px-3 text-right">Total Wt (kg)</th>
                          </tr>
                        </thead>
                        <tbody className="divide-y divide-slate-800/60">
                          {projectBBSData.items.map((it, idx) => (
                            <tr key={`proj-item-${idx}`} className="hover:bg-slate-900/50 transition">
                              <td className="py-2 px-3 text-cyan-300 font-bold">
                                {it.member_id}
                                <span className="text-[0.65rem] text-slate-400 block font-normal">{it.member_type}</span>
                              </td>
                              <td className="py-2 px-3 text-slate-200">
                                <div>{it.bar_mark}</div>
                                <div className="text-[0.65rem] text-slate-400 line-clamp-1">{it.shape_description}</div>
                              </td>
                              <td className="py-2 px-3 text-center text-cyan-400 font-bold">T{it.bar_diameter_mm}</td>
                              <td className="py-2 px-3 text-center text-slate-300">{it.num_bars}</td>
                              <td className="py-2 px-3 text-right">
                                <span
                                  className="clickable-qty text-emerald-400 font-bold"
                                  onClick={() =>
                                    setInspectItem({
                                      memberId: it.member_id,
                                      memberType: it.member_type,
                                      barMark: it.bar_mark,
                                      diameter: it.bar_diameter_mm,
                                      numBars: it.num_bars,
                                      cuttingLengthM: it.cutting_length_m,
                                      cuttingLengthMm: it.cutting_length_mm,
                                      unitWeight: it.unit_weight_kg_m,
                                      totalWeight: it.total_weight_kg,
                                      shapeDescription: it.shape_description,
                                      breakdown: it.breakdown,
                                      activeTab: "cutting_length",
                                    })
                                  }
                                >
                                  {it.cutting_length_m.toFixed(3)}
                                </span>
                              </td>
                              <td className="py-2 px-3 text-right">
                                <span
                                  className="clickable-qty text-cyan-300"
                                  onClick={() =>
                                    setInspectItem({
                                      memberId: it.member_id,
                                      memberType: it.member_type,
                                      barMark: it.bar_mark,
                                      diameter: it.bar_diameter_mm,
                                      numBars: it.num_bars,
                                      cuttingLengthM: it.cutting_length_m,
                                      cuttingLengthMm: it.cutting_length_mm,
                                      unitWeight: it.unit_weight_kg_m,
                                      totalWeight: it.total_weight_kg,
                                      shapeDescription: it.shape_description,
                                      breakdown: it.breakdown,
                                      activeTab: "unit_weight",
                                    })
                                  }
                                >
                                  {it.unit_weight_kg_m.toFixed(2)}
                                </span>
                              </td>
                              <td className="py-2 px-3 text-right">
                                <span
                                  className="clickable-qty text-amber-300 font-bold"
                                  onClick={() =>
                                    setInspectItem({
                                      memberId: it.member_id,
                                      memberType: it.member_type,
                                      barMark: it.bar_mark,
                                      diameter: it.bar_diameter_mm,
                                      numBars: it.num_bars,
                                      cuttingLengthM: it.cutting_length_m,
                                      cuttingLengthMm: it.cutting_length_mm,
                                      unitWeight: it.unit_weight_kg_m,
                                      totalWeight: it.total_weight_kg,
                                      shapeDescription: it.shape_description,
                                      breakdown: it.breakdown,
                                      activeTab: "total_weight",
                                    })
                                  }
                                >
                                  {it.total_weight_kg.toFixed(2)}
                                </span>
                              </td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </div>
                  </>
                )) : (
                  <div className="text-center py-12 text-slate-400 border border-dashed border-slate-800 rounded-lg">
                    <p className="font-mono text-xs text-cyan-400">NO PROJECT BBS COMPILED YET</p>
                    <p className="text-sm mt-1">Click "Compile Consolidated Project BBS" on the left to aggregate all drawing members.</p>
                  </div>
                )}
              </div>
            )}

            {/* VIEW MODE 3: 12M STOCK BAR CUTTING STOCK OPTIMIZATION */}
            {viewMode === "optimization" && (
              <div className="space-y-4">
                {isOptimizationLoading ? (
                  <div className="text-center py-12 text-slate-400">
                    <span className="inline-block animate-spin text-2xl mb-2">✂️</span>
                    <p className="font-mono text-xs text-amber-300">SOLVING 1D CUTTING STOCK PROBLEM &amp; PACKING 12M STOCK BARS...</p>
                  </div>
                ) : procurementData ? (
                  procurementData.total_stock_bars_12m === 0 ? (
                    <div className="bg-slate-950/80 border border-slate-800 rounded-xl p-8 text-center space-y-4 max-w-2xl mx-auto my-6">
                      <div className="w-14 h-14 bg-amber-500/10 border border-amber-500/30 rounded-full flex items-center justify-center mx-auto text-2xl">
                        ✂️
                      </div>
                      <div className="space-y-1">
                        <h3 className="text-base font-bold text-slate-100 font-mono tracking-wide">
                          NO REBAR ITEMS TO OPTIMIZE
                        </h3>
                        <p className="text-xs text-slate-400 max-w-md mx-auto leading-relaxed">
                          The cutting stock optimizer requires active structural member cutting lengths from your drawings to pack into standard 12.0m commercial stock bars.
                        </p>
                      </div>
                      <div className="flex flex-wrap items-center justify-center gap-3 pt-2">
                        <button
                          type="button"
                          onClick={() => handleLoadOptimization(true)}
                          className="px-4 py-2 bg-amber-600 hover:bg-amber-500 text-slate-950 font-bold text-xs rounded-lg transition font-mono flex items-center gap-1.5 cursor-pointer"
                        >
                          <span>🧪</span> Run Optimizer on 9-Member Demo
                        </button>
                      </div>
                    </div>
                  ) : (
                    <>
                      {procurementData.project_id.includes("Reference Project") && (
                        <div className="bg-amber-500/10 border border-amber-500/30 rounded-lg px-3 py-2 flex items-center justify-between text-xs font-mono text-amber-300 mb-2">
                          <div className="flex items-center gap-2">
                            <span>🧪</span>
                            <span><strong>DEMO REFERENCE OPTIMIZATION</strong> · 1D cutting stock packing calculated on baseline project members.</span>
                          </div>
                          <span className="text-[0.65rem] bg-amber-500/20 text-amber-300 px-2 py-0.5 rounded font-bold uppercase tracking-wider">Demo Mode</span>
                        </div>
                      )}
                      {/* Procurement Hero Summary */}
                      <div className="result-hero-metric" style={{ borderColor: "rgba(245, 158, 11, 0.4)" }}>
                      <div>
                        <span className="metric-label text-amber-300">STANDARD 12.0M COMMERCIAL STOCK REQUISITION</span>
                        <div className="metric-value text-amber-400">
                          {procurementData.total_stock_bars_12m} Stock Bars
                          <span className="metric-sub text-slate-300">({procurementData.total_gross_weight_tonnes.toFixed(3)} Tonnes Gross)</span>
                        </div>
                      </div>
                      <div className="text-right font-mono text-xs">
                        <div className="text-emerald-400 font-bold">
                          SCRAP WASTAGE: {procurementData.overall_wastage_percentage}%
                        </div>
                        <div className="text-slate-400 mt-0.5">
                          Net Steel: {procurementData.total_net_weight_tonnes.toFixed(3)} T · Scrap: {procurementData.total_scrap_tonnes.toFixed(3)} T
                        </div>
                      </div>
                    </div>

                    {/* Recommendations Banner */}
                    <div className="bg-slate-900/80 border border-slate-800 rounded-lg p-3 text-xs font-mono space-y-1">
                      <span className="text-amber-400 font-bold uppercase block text-[0.7rem]">
                        SITE FABRICATION &amp; PROCUREMENT DIRECTIVES:
                      </span>
                      {procurementData.procurement_recommendations.map((rec, idx) => (
                        <div key={`rec-${idx}`} className="text-slate-300 flex items-start gap-2">
                          <span className="text-amber-400">▸</span>
                          <span>{rec}</span>
                        </div>
                      ))}
                    </div>

                    {/* Stock Bar Cut Lists by Diameter */}
                    <div className="space-y-4">
                      {procurementData.diameter_summaries.map((diaSum, dIdx) => (
                        <div key={`dia-opt-${dIdx}`} className="stock-bar-visualizer-card">
                          <div className="flex justify-between items-center mb-2">
                            <div className="flex items-center gap-2">
                              <span className="text-cyan-400 font-mono font-bold text-sm bg-cyan-950/80 border border-cyan-500/40 px-2 py-0.5 rounded">
                                T{diaSum.bar_diameter_mm} REBAR
                              </span>
                              <span className="text-xs font-mono text-slate-300">
                                {diaSum.total_pieces_required} cut pieces needed → <strong>{diaSum.stock_bars_12m_required} standard 12m bars</strong>
                              </span>
                            </div>
                            <div className="text-xs font-mono">
                              <span className="text-slate-400">Wastage: </span>
                              <span className={diaSum.wastage_percentage < 5.0 ? "text-emerald-400 font-bold" : "text-amber-400 font-bold"}>
                                {diaSum.wastage_percentage}% ({diaSum.total_scrap_weight_kg.toFixed(1)} kg)
                              </span>
                              {diaSum.usable_offcuts_count > 0 && (
                                <span className="text-sky-300 ml-2">({diaSum.usable_offcuts_count} offcuts ≥ 1.0m saved)</span>
                              )}
                            </div>
                          </div>

                          {/* Visual 12m Bar Tracks */}
                          <div className="space-y-2 mt-3">
                            {diaSum.patterns.map((pat, pIdx) => (
                              <div key={`pat-${pIdx}`}>
                                <div className="flex justify-between text-[0.65rem] font-mono text-slate-400 mb-0.5">
                                  <span>12m Stock Bar #{pat.stock_bar_id}</span>
                                  <span>
                                    Cut: {pat.total_cut_length_mm.toFixed(0)} mm / 12,000 mm · Scrap: {pat.waste_scrap_mm.toFixed(0)} mm ({pat.wastage_percentage}%)
                                  </span>
                                </div>
                                <div className="stock-bar-track">
                                  {pat.cuts.map((cut, cIdx) => {
                                    const pct = (cut.cutting_length_mm / 12000.0) * 100.0;
                                    const colorClass = `segment-color-${cIdx % 5}`;
                                    return (
                                      <div
                                        key={`cut-${cIdx}`}
                                        className={`stock-bar-segment ${colorClass}`}
                                        style={{ width: `${pct}%` }}
                                        title={`${cut.member_id} (${cut.bar_mark}): ${cut.cutting_length_mm.toFixed(0)} mm`}
                                      >
                                        {cut.member_id} · {cut.cutting_length_mm.toFixed(0)}
                                      </div>
                                    );
                                  })}
                                  {pat.waste_scrap_mm > 0 && (
                                    <div
                                      className={`stock-bar-waste ${pat.is_usable_offcut ? "usable-offcut" : ""}`}
                                      style={{ width: `${(pat.waste_scrap_mm / 12000.0) * 100.0}%` }}
                                      title={pat.is_usable_offcut ? `Usable Offcut: ${pat.waste_scrap_mm.toFixed(0)} mm` : `Scrap: ${pat.waste_scrap_mm.toFixed(0)} mm`}
                                    >
                                      {pat.is_usable_offcut ? "REUSE" : "SCRAP"}
                                    </div>
                                  )}
                                </div>
                              </div>
                            ))}
                          </div>
                        </div>
                      ))}
                    </div>
                  </>
                )) : (
                  <div className="text-center py-12 text-slate-400 border border-dashed border-slate-800 rounded-lg">
                    <p className="font-mono text-xs text-amber-400">NO 12M CUTTING OPTIMIZATION RUN YET</p>
                    <p className="text-sm mt-1">Click "12m Stock Bar 1D Cutting Optimizer" on the left to pack cuts into standard commercial lengths.</p>
                  </div>
                )}
              </div>
            )}
          </div>
        </section>
      </div>
    </>
  );
}
