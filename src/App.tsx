import { useCallback, useEffect, useMemo, useState } from "react";
import {
  Apple, ArrowDownToLine, ArrowRight, BadgeCheck, Bell, Bike, Check, ChevronDown, Clock3,
  Flame, Heart, ImagePlus, LogOut, MapPin, Menu, PackageCheck, Plus, ShieldCheck,
  Sparkles, Users, Utensils, X,
} from "lucide-react";
import { api, type AdminMetrics, type Delivery, type Listing, type Match, type NetworkSnapshot, type PendingOrganization, type Role, type User, socketUrl } from "./api";
import LiveMap from "./LiveMap";

const roles: { id: Role; label: string; icon: typeof Users }[] = [
  { id: "admin", label: "Network admin", icon: ShieldCheck },
  { id: "donor", label: "Food donor", icon: Utensils },
  { id: "recipient", label: "Recipient", icon: Heart },
  { id: "volunteer", label: "Volunteer", icon: Bike },
];

const demoListings: Listing[] = [
  { id: 1, title: "Fresh vegetable biryani", category: "Prepared meals", portions: 25, status: "available", pickup_deadline: new Date(Date.now() + 2 * 3600000).toISOString(), donor_name: "The Green Table", latitude: 12.9716, longitude: 77.5946 },
  { id: 2, title: "Assorted bakery boxes", category: "Bakery", portions: 18, status: "matched", pickup_deadline: new Date(Date.now() + 90 * 60000).toISOString(), donor_name: "Morning Crust", latitude: 12.976, longitude: 77.602 },
  { id: 3, title: "Seasonal fruit baskets", category: "Produce", portions: 32, status: "available", pickup_deadline: new Date(Date.now() + 3 * 3600000).toISOString(), donor_name: "Harvest Kitchen", latitude: 12.964, longitude: 77.586 },
];

const demoMatches: Match[] = [
  { match_id: 1, listing_id: 1, request_id: 1, listing_title: "Fresh vegetable biryani", recipient_name: "Sunrise Care Home", score: 96, explanation: "25 portions meet the exact need. No allergen conflicts, with an estimated 10-minute journey.", portions: 25 },
  { match_id: 2, listing_id: 3, request_id: 2, listing_title: "Seasonal fruit baskets", recipient_name: "Little Steps Foundation", score: 88, explanation: "High-urgency request nearby; fresh produce fits the organization's dietary preferences.", portions: 32 },
];

const roleCopy: Record<Role, { eyebrow: string; title: string; description: string; action: string }> = {
  admin: { eyebrow: "DISTRICT OVERVIEW", title: "Good morning, Alex", description: "Here's what's happening across your food rescue network today.", action: "Review verifications" },
  donor: { eyebrow: "DONOR DASHBOARD", title: "Good morning, Maya", description: "Every surplus meal can make a difference in your neighborhood.", action: "List surplus food" },
  recipient: { eyebrow: "COMMUNITY DASHBOARD", title: "Good morning, Priya", description: "Find fresh, safe food for the people who count on you.", action: "Post a meal request" },
  volunteer: { eyebrow: "VOLUNTEER DASHBOARD", title: "Good morning, Jordan", description: "A little time can turn surplus into something meaningful.", action: "Find a pickup" },
};

function App() {
  const [role, setRole] = useState<Role>("admin");
  const [user, setUser] = useState<User | null>(null);
  const [listings, setListings] = useState<Listing[]>(demoListings);
  const [matches, setMatches] = useState<Match[]>(demoMatches);
  const [notice, setNotice] = useState("");
  const [error, setError] = useState("");
  const [dialog, setDialog] = useState<"listing" | "request" | "login" | "register" | "none">("none");
  const [mobileMenu, setMobileMenu] = useState(false);
  const [network, setNetwork] = useState<NetworkSnapshot | null>(null);
  const [deliveries, setDeliveries] = useState<Delivery[]>([]);
  const [pendingOrganizations, setPendingOrganizations] = useState<PendingOrganization[]>([]);
  const [adminMetrics, setAdminMetrics] = useState<AdminMetrics | null>(null);
  const [volunteerPoints, setVolunteerPoints] = useState(0);
  const [trackingDeliveryId, setTrackingDeliveryId] = useState<number | null>(null);

  const refresh = useCallback(async () => {
    if (!localStorage.getItem("foodbridge-token")) return;
    try {
      const current = await api<User>("/auth/me");
      setUser(current);
      setRole(current.role);
      const data = await api<Listing[]>("/listings");
      setListings(data);
      setNetwork(await api<NetworkSnapshot>("/network/locations"));
      setDeliveries(await api<Delivery[]>("/deliveries"));
      if (current.role === "volunteer") {
        const points = await api<{ total: number }>("/volunteers/me/points");
        setVolunteerPoints(points.total);
      }
      if (current.role === "admin") {
        const [organizations, metrics] = await Promise.all([
          api<PendingOrganization[]>("/admin/organizations/pending"),
          api<AdminMetrics>("/admin/metrics"),
        ]);
        setPendingOrganizations(organizations);
        setAdminMetrics(metrics);
      }
      if (current.role === "recipient" || current.role === "admin") {
        const ranked = await api<Match[]>("/match/prioritize");
        setMatches(ranked);
      }
      setError("");
    } catch (e) {
      setError(e instanceof Error ? e.message : "Could not load your account.");
    }
  }, []);

  useEffect(() => { void refresh(); }, [refresh]);

  useEffect(() => {
    if (!localStorage.getItem("foodbridge-token")) return;
    const socket = new WebSocket(socketUrl());
    socket.onmessage = () => { void refresh(); };
    socket.onerror = () => setError("Live updates disconnected. Refresh to reconnect.");
    return () => socket.close();
  }, [refresh, user]);

  useEffect(() => {
    if (trackingDeliveryId === null || !navigator.geolocation) return;
    let lastSentAt = 0;
    const watchId = navigator.geolocation.watchPosition((position) => {
      if (Date.now() - lastSentAt < 10000) return;
      lastSentAt = Date.now();
      void api(`/deliveries/${trackingDeliveryId}/location`, {
        method: "PATCH",
        body: JSON.stringify({ latitude: position.coords.latitude, longitude: position.coords.longitude }),
      }).catch((e: unknown) => setError(e instanceof Error ? e.message : "Could not update live location."));
    }, () => setError("Location permission is needed to share your live route."), { enableHighAccuracy: true, maximumAge: 5000 });
    return () => navigator.geolocation.clearWatch(watchId);
  }, [trackingDeliveryId]);

  const stats = useMemo(() => {
    const completed = adminMetrics?.completed_deliveries ?? 0;
    const rescinded = adminMetrics?.rescinded_deliveries ?? 0;
    const successRate = completed + rescinded ? `${Math.round(completed / (completed + rescinded) * 100)}%` : "—";
    return [
      { label: role === "donor" ? "Meals listed" : "Meals rescued", value: adminMetrics ? adminMetrics.meals_saved.toLocaleString() : role === "donor" ? "1,284" : "2,480", change: adminMetrics ? "Completed deliveries" : "+12% this month", icon: Utensils, color: "mint" },
      { label: role === "recipient" ? "Organizations supported" : "Active organizations", value: adminMetrics ? String(adminMetrics.recipient_organizations_supported) : "38", change: adminMetrics ? "Verified recipients" : "+4 this week", icon: Heart, color: "peach" },
      { label: role === "admin" && adminMetrics ? "Safety rejections" : "Active deliveries", value: role === "admin" && adminMetrics ? String(adminMetrics.safety_rejections) : user ? String(deliveries.filter((item) => item.status !== "completed").length) : "12", change: role === "admin" && adminMetrics ? "Food listings rejected" : "Across your district", icon: Bike, color: "lavender" },
      { label: role === "volunteer" ? "Your rescue points" : "Rescue success rate", value: role === "volunteer" ? (user ? volunteerPoints.toLocaleString() : "640") : adminMetrics ? successRate : "94.8%", change: role === "volunteer" ? "Earned from completed rescues" : adminMetrics ? "Completed vs. rescinded" : "+2.4% this month", icon: Flame, color: "yellow" },
    ];
  }, [adminMetrics, deliveries, role, user, volunteerPoints]);
  const copy = roleCopy[role];

  async function createListing(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    try {
      const listing = await api<Listing>("/listings", {
        method: "POST",
        body: JSON.stringify({
          title: form.get("title"), category: form.get("category"), portions: Number(form.get("portions")),
          prepared_at: new Date(String(form.get("prepared_at"))).toISOString(),
          pickup_deadline: new Date(String(form.get("pickup_deadline"))).toISOString(),
          packaging: form.get("packaging"), storage: form.get("storage"),
          allergens: String(form.get("allergens") ?? "").split(",").map((item) => item.trim()).filter(Boolean),
          safety_confirmed: form.get("safety") === "on",
        }),
      });
      setListings((existing) => [listing, ...existing]);
      setDialog("none");
      setNotice("Your food listing is live and ready to be matched.");
    } catch (e) { setError(e instanceof Error ? e.message : "Could not publish listing."); }
  }

  async function createRequest(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    try {
      await api("/requests", { method: "POST", body: JSON.stringify({
        meals_needed: Number(form.get("meals")), dietary_restrictions: String(form.get("diet") ?? "").split(",").map((v) => v.trim()).filter(Boolean),
        cutoff_at: new Date(String(form.get("cutoff"))).toISOString(),
      }) });
      setDialog("none");
      setNotice("Your meal request has been posted.");
      await refresh();
    } catch (e) { setError(e instanceof Error ? e.message : "Could not post request."); }
  }

  async function acceptMatch(item: Match) {
    try {
      await api("/matches/accept", { method: "POST", body: JSON.stringify({ listing_id: item.listing_id, request_id: item.request_id }) });
      setMatches((current) => current.filter((entry) => entry.listing_id !== item.listing_id));
      setNotice("Match accepted. Volunteers can now claim the delivery.");
    } catch (e) { setError(e instanceof Error ? e.message : "Could not accept match."); }
  }

  async function overrideMatch(item: Match) {
    try {
      const score = Math.min(100, item.score + 5);
      await api(`/admin/matches/${item.match_id}/priority`, {
        method: "PATCH",
        body: JSON.stringify({ score, explanation: `Admin priority override: elevated to ${score}/100. ${item.explanation}`.slice(0, 500) }),
      });
      setMatches((current) => current.map((match) => match.match_id === item.match_id ? { ...match, score } : match));
      setNotice("Match priority updated.");
    } catch (e) { setError(e instanceof Error ? e.message : "Could not override match priority."); }
  }

  async function rejectSafety(listing: Listing) {
    try {
      await api(`/admin/listings/${listing.id}/safety-reject`, { method: "POST" });
      setListings((current) => current.map((item) => item.id === listing.id ? { ...item, status: "safety_rejected" } : item));
      setNotice("Listing rejected for a food safety review.");
      await refresh();
    } catch (e) { setError(e instanceof Error ? e.message : "Could not reject listing."); }
  }

  async function verifyOrganization(organizationId: number) {
    try {
      await api(`/admin/organizations/${organizationId}/verify`, { method: "POST" });
      setPendingOrganizations((items) => items.filter((item) => item.id !== organizationId));
      setNotice("Organization verified and can now use FoodBridge.");
      await refresh();
    } catch (e) { setError(e instanceof Error ? e.message : "Could not verify organization."); }
  }

  async function claimDelivery(deliveryId: number) {
    try {
      await api(`/deliveries/${deliveryId}/claim`, { method: "POST" });
      setNotice("Pickup claimed. Start sharing your location when you begin the route.");
      await refresh();
    } catch (e) { setError(e instanceof Error ? e.message : "Could not claim pickup."); }
  }

  async function cancelDelivery(deliveryId: number) {
    try {
      await api(`/deliveries/${deliveryId}/cancel`, { method: "POST" });
      setTrackingDeliveryId(null);
      setNotice("Pickup released for reassignment to another volunteer.");
      await refresh();
    } catch (e) { setError(e instanceof Error ? e.message : "Could not release pickup."); }
  }

  async function uploadProof(deliveryId: number, image: File) {
    if (!navigator.geolocation) { setError("This device does not provide location access for proof of delivery."); return; }
    navigator.geolocation.getCurrentPosition(async (position) => {
      try {
        const body = new FormData();
        body.append("image", image);
        await api(`/deliveries/${deliveryId}/proof?latitude=${position.coords.latitude}&longitude=${position.coords.longitude}`, { method: "POST", body });
        setNotice("Time-stamped, location-tagged delivery photo uploaded.");
        await refresh();
      } catch (e) { setError(e instanceof Error ? e.message : "Could not upload delivery proof."); }
    }, () => setError("Location access is required to geo-tag delivery proof."), { enableHighAccuracy: true, timeout: 10000 });
  }

  async function completeDelivery(deliveryId: number) {
    try {
      await api(`/deliveries/${deliveryId}/complete`, { method: "POST" });
      setTrackingDeliveryId(null);
      setNotice("Delivery completed. 50 volunteer points earned!");
      await refresh();
    } catch (e) { setError(e instanceof Error ? e.message : "Could not complete delivery."); }
  }

  async function login(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    try {
      const data = await api<{ access_token: string }>("/auth/login", { method: "POST", body: JSON.stringify({ email: form.get("email"), password: form.get("password") }) });
      localStorage.setItem("foodbridge-token", data.access_token);
      setDialog("none");
      await refresh();
    } catch (e) { setError(e instanceof Error ? e.message : "Could not sign in."); }
  }

  async function register(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    const roleValue = String(form.get("role")) as "donor" | "recipient" | "volunteer";
    try {
      await api("/auth/register", { method: "POST", body: JSON.stringify({
        email: form.get("email"), password: form.get("password"), full_name: form.get("full_name"),
        role: roleValue, organization_name: form.get("organization_name") || undefined,
        latitude: form.get("latitude") ? Number(form.get("latitude")) : undefined,
        longitude: form.get("longitude") ? Number(form.get("longitude")) : undefined,
      }) });
      setDialog("login");
      setNotice(roleValue === "volunteer" ? "Account created. Sign in to get started." : "Account created. Your organization will be able to contribute after admin verification.");
    } catch (e) { setError(e instanceof Error ? e.message : "Could not create account."); }
  }

  function signOut() {
    localStorage.removeItem("foodbridge-token");
    setUser(null);
    setRole("admin");
  }

  const openAction = () => {
    if (role === "donor") setDialog("listing");
    else if (role === "recipient") setDialog("request");
    else if (role === "volunteer") document.getElementById("opportunities")?.scrollIntoView({ behavior: "smooth" });
    else document.getElementById("verification")?.scrollIntoView({ behavior: "smooth" });
  };

  return (
    <div className="app-shell">
      <aside className={`sidebar ${mobileMenu ? "sidebar-open" : ""}`}>
        <div className="brand"><div className="brand-mark"><Apple size={19} fill="currentColor" /></div><span>foodbridge</span></div>
        <div className="workspace-label">WORKSPACE</div>
        <button className="workspace-picker"><div className="workspace-avatar">N</div><span><b>North District</b><small>Community network</small></span><ChevronDown size={16} /></button>
        <div className="nav-label">MENU</div>
        <nav className="main-nav">
          <a className="nav-item active" href="#overview"><span className="nav-symbol"><Sparkles size={18} /></span>Overview</a>
          <a className="nav-item" href="#listings"><span className="nav-symbol"><PackageCheck size={18} /></span>Food listings<span className="nav-badge">{listings.length}</span></a>
          <a className="nav-item" href="#opportunities"><span className="nav-symbol"><Heart size={18} /></span>Smart matches<span className="nav-badge">{matches.length}</span></a>
          <a className="nav-item" href="#map"><span className="nav-symbol"><MapPin size={18} /></span>Live map</a>
          <a className="nav-item" href="#verification"><span className="nav-symbol"><BadgeCheck size={18} /></span>Verifications<span className="nav-badge warm">3</span></a>
        </nav>
        <div className="side-bottom">
          <div className="help-card"><div className="help-icon"><Heart size={17} /></div><b>Good things add up.</b><p>Your network has rescued 2,480 meals this month.</p><a href="#impact">See your impact <ArrowRight size={13} /></a></div>
          <button className="profile" onClick={() => user ? signOut() : setDialog("login")}><div className="profile-avatar">{user?.name.slice(0, 1) ?? "A"}</div><span><b>{user?.name ?? "Alex Morgan"}</b><small>{user?.role ?? "Network admin"}</small></span>{user ? <LogOut size={15} /> : <ChevronDown size={16} />}</button>
        </div>
      </aside>

      <main className="main-content" id="overview">
        <header className="topbar">
          <button className="icon-btn menu-toggle" aria-label="Open menu" onClick={() => setMobileMenu(!mobileMenu)}><Menu size={19} /></button>
          <div className="breadcrumbs">North District <span>/</span> <b>{roles.find((r) => r.id === role)?.label}</b></div>
          <div className="topbar-right">
            <label className="role-switch"><span>{user ? "Account role" : "Viewing as"}</span><select value={role} disabled={!!user} onChange={(e) => setRole(e.target.value as Role)} aria-label="Switch dashboard role">{roles.map((item) => <option value={item.id} key={item.id}>{item.label}</option>)}</select><ChevronDown size={14} /></label>
            <button className="icon-btn notification-btn" aria-label="Notifications"><Bell size={18} /><i /></button>
            <button className="user-chip" onClick={() => user ? signOut() : setDialog("login")}><div className="profile-avatar small">{user?.name.slice(0, 1) ?? "A"}</div><ChevronDown size={14} /></button>
          </div>
        </header>

        <div className="content-wrap">
          {error && <div className="alert error">{error}<button onClick={() => setError("")}><X size={15} /></button></div>}
          {notice && <div className="alert success"><Check size={16} />{notice}<button onClick={() => setNotice("")}><X size={15} /></button></div>}
          <section className="welcome-row">
            <div><div className="eyebrow"><span className="live-dot" />{copy.eyebrow}</div><h1>{copy.title}</h1><p>{copy.description}</p></div>
            <button className="primary-btn" onClick={openAction}><Plus size={17} />{copy.action}<ArrowRight size={16} /></button>
          </section>

          <section className="stats-grid" id="impact">
            {stats.map((item) => <article className="stat-card" key={item.label}><div className={`stat-icon ${item.color}`}><item.icon size={19} /></div><div className="stat-label">{item.label}</div><div className="stat-value">{item.value}</div><div className="stat-change"><span>↗</span> {item.change}</div><div className="stat-sparkline" aria-hidden="true"><i /><i /><i /><i /><i /><i /><i /><i /><i /></div></article>)}
          </section>

          <section className="section-row"><div><div className="section-title"><h2>Rescue activity</h2><span className="live-pill"><i /> Live</span></div><p className="section-subtitle">A real-time view of your neighborhood network</p></div><button className="subtle-btn"><span className="tiny-square" /> This week <ChevronDown size={14} /></button></section>

          <section className="map-panel" id="map"><div className="map-heading"><div><h3>North District</h3><span><MapPin size={13} /> Bengaluru, India</span></div><button className="map-expand" aria-label="Expand map"><ArrowDownToLine size={15} /></button></div><LiveMap listings={listings} network={network} /></section>

          <section className="lower-grid">
            <div className="panel listings-panel" id="listings"><div className="panel-head"><div><h2>{role === "volunteer" ? "Nearby pickups" : "Recent food listings"}</h2><p>Surplus food ready to make a difference</p></div><button className="text-link">View all <ArrowRight size={14} /></button></div>
              <div className="listing-list">{listings.slice(0, 3).map((listing, index) => <article className="listing-row" key={listing.id}><div className={`food-thumb food-${index}`}><Utensils size={19} /></div><div className="listing-main"><b>{listing.title}</b><span>{listing.donor_name ?? "Community donor"} · {listing.category}</span></div><div className="listing-portions"><b>{listing.portions}</b><span>portions</span></div><span className={`status-tag ${listing.status === "available" ? "status-green" : "status-blue"}`}><i />{listing.status === "available" ? "Available" : listing.status}</span><div className="deadline"><Clock3 size={14} />{Math.max(1, Math.round((new Date(listing.pickup_deadline).getTime() - Date.now()) / 3600000))}h left</div>{user?.role === "admin" && listing.status !== "completed" && listing.status !== "safety_rejected" && <button className="decline-btn safety-action" onClick={() => void rejectSafety(listing)}>Safety reject</button>}<button className="row-more" aria-label={`More about ${listing.title}`}><ChevronDown size={17} /></button></article>)}</div>
            </div>

            <div className="panel match-panel" id="opportunities"><div className="panel-head"><div><h2>{role === "volunteer" ? "Pickup opportunities" : "Recommended matches"}</h2><p>{role === "volunteer" ? "Accepted donations ready for delivery" : "Thoughtful matches, powered by local AI"}</p></div><span className="ai-chip"><Sparkles size={13} /> AI matched</span></div>
              <div className="match-list">{role === "volunteer" ? deliveries.map((delivery) => <article className="match-card" key={delivery.id}><div className="match-card-top"><div className="match-icon"><Bike size={17} /></div><div className="match-info"><b>{delivery.listing_title || `Food pickup #${delivery.id}`}</b><span>Deliver to {delivery.recipient_name || "recipient organization"}</span></div><span className={`status-tag ${delivery.status === "available" ? "status-green" : "status-blue"}`}>{delivery.status}</span></div><p>Pickup #{delivery.listing_id} · delivery #{delivery.id}. Confirm handover with a geo-tagged photo.</p><div className="match-actions">{delivery.status === "available" ? <button className="accept-btn" onClick={() => void claimDelivery(delivery.id)}><Check size={14} /> Claim pickup</button> : <><button className="accept-btn" onClick={() => setTrackingDeliveryId(trackingDeliveryId === delivery.id ? null : delivery.id)}><MapPin size={14} /> {trackingDeliveryId === delivery.id ? "Stop sharing" : "Share live route"}</button><label className="decline-btn proof-upload">{delivery.proof_uploaded ? "Proof uploaded" : "Capture proof"}<input type="file" accept="image/*" capture="environment" disabled={delivery.proof_uploaded} onChange={(e) => { const photo = e.target.files?.[0]; if (photo) void uploadProof(delivery.id, photo); }} /></label>{delivery.proof_uploaded && <button className="accept-btn" onClick={() => void completeDelivery(delivery.id)}>Complete delivery</button>}<button className="decline-btn" onClick={() => void cancelDelivery(delivery.id)}>Emergency cancel</button></>}</div></article>) : matches.slice(0, 2).map((item) => <article className="match-card" key={item.listing_id}><div className="match-card-top"><div className="match-icon"><Heart size={17} /></div><div className="match-info"><b>{item.recipient_name}</b><span>Needs {item.portions} meals · 10 min away</span></div><span className="score">{item.score}<small>%</small></span></div><p>{item.explanation}</p><div className="match-actions"><button className="accept-btn" onClick={() => void acceptMatch(item)}><Check size={14} /> Accept match</button><button className="decline-btn" onClick={() => setMatches((current) => current.filter((match) => match.listing_id !== item.listing_id))}>Not now</button>{user?.role === "admin" && <button className="decline-btn" onClick={() => void overrideMatch(item)}>Raise priority</button>}</div></article>)}
                {!(role === "volunteer" ? deliveries.length : matches.length) && <div className="empty-state">No new opportunities right now. We'll keep looking.</div>}
              </div>
            </div>
          </section>

          <section className="bottom-grid">
            <div className="panel verification-panel" id="verification"><div className="panel-head"><div><h2>{user && role === "admin" ? "Organization verifications" : "Needs your attention"}</h2><p>{user && role === "admin" ? "Review new network participants" : "Small actions, big community impact"}</p></div><span className="count-badge">{user && role === "admin" ? pendingOrganizations.length : "3"}</span></div>{user && role === "admin" ? pendingOrganizations.length ? pendingOrganizations.slice(0, 4).map((organization) => <div className="attention-row" key={organization.id}><div className="attention-icon orange"><BadgeCheck size={17} /></div><div><b>{organization.name}</b><span>{organization.kind} · submitted {new Date(organization.created_at).toLocaleDateString()}</span></div><button className="accept-btn" onClick={() => void verifyOrganization(organization.id)}>Verify</button></div>) : <div className="empty-state">No organizations are waiting for verification.</div> : <><div className="attention-row"><div className="attention-icon orange"><BadgeCheck size={17} /></div><div><b>Organization verifications</b><span>3 new organizations are waiting for review</span></div><button className="round-arrow"><ArrowRight size={15} /></button></div><div className="attention-row"><div className="attention-icon blue"><Bike size={17} /></div><div><b>Delivery needs a volunteer</b><span>2 accepted matches need a pickup partner</span></div><button className="round-arrow"><ArrowRight size={15} /></button></div></>}</div>
            <div className="impact-card"><div className="impact-top"><div className="impact-icon"><Flame size={18} /></div><span>YOUR COMMUNITY IMPACT</span></div><div className="impact-number">2,480 <small>meals</small></div><p>rescued and shared across North District this month.</p><div className="impact-progress"><i /></div><div className="impact-foot"><span>Monthly goal: 3,000 meals</span><b>83%</b></div><div className="impact-decoration"><Heart size={80} /></div></div>
          </section>
          <footer>Made with care for a world with less waste. <Heart size={13} fill="currentColor" /></footer>
        </div>
      </main>
      {mobileMenu && <button className="mobile-backdrop" aria-label="Close menu" onClick={() => setMobileMenu(false)} />}
      {dialog !== "none" && <div className="modal-backdrop" onMouseDown={(e) => { if (e.target === e.currentTarget) setDialog("none"); }}><section className="modal"><div className="modal-head"><div><span className="eyebrow">{dialog === "login" ? "WELCOME BACK" : "FOODBRIDGE"}</span><h2>{dialog === "listing" ? "List surplus food" : dialog === "request" ? "Post a meal request" : dialog === "register" ? "Create your account" : "Sign in to FoodBridge"}</h2></div><button className="icon-btn" onClick={() => setDialog("none")} aria-label="Close"><X size={18} /></button></div>
        {error && <div className="alert error">{error}<button onClick={() => setError("")}><X size={15} /></button></div>}
        {dialog === "listing" && <form onSubmit={createListing} className="modal-form"><label>Food name<input name="title" placeholder="e.g. Vegetable biryani" required /></label><div className="form-pair"><label>Category<select name="category"><option>Prepared meals</option><option>Bakery</option><option>Produce</option><option>Dairy</option></select></label><label>Meal portions<input name="portions" type="number" min="1" required placeholder="25" /></label></div><div className="form-pair"><label>Prepared at<input name="prepared_at" type="datetime-local" required /></label><label>Pickup deadline<input name="pickup_deadline" type="datetime-local" required /></label></div><div className="form-pair"><label>Packaging<input name="packaging" required placeholder="Sealed containers" /></label><label>Storage conditions<input name="storage" required placeholder="Refrigerated" /></label></div><label>Allergens <span className="muted">(comma separated)</span><input name="allergens" placeholder="e.g. dairy, nuts" /></label><ImageAnalysis onSuggestion={(suggestion) => { const title = document.querySelector<HTMLInputElement>('input[name="title"]'); if (title && suggestion) title.value = suggestion; }} /><label className="check-label"><input type="checkbox" name="safety" required /> I confirm this food was handled and stored safely.</label><button className="primary-btn full-btn"><Plus size={16} /> Publish listing</button></form>}
        {dialog === "request" && <form onSubmit={createRequest} className="modal-form"><label>Meals needed<input name="meals" type="number" min="1" required placeholder="25" /></label><label>Dietary restrictions <span className="muted">(comma separated)</span><input name="diet" placeholder="vegetarian, no peanuts" /></label><label>Request cutoff<input name="cutoff" type="datetime-local" required /></label><button className="primary-btn full-btn"><Plus size={16} /> Post meal request</button></form>}
        {dialog === "login" && <form onSubmit={login} className="modal-form"><p className="muted">Sign in with your verified FoodBridge account.</p><label>Email<input name="email" type="email" autoComplete="email" required placeholder="you@organization.org" /></label><label>Password<input name="password" type="password" autoComplete="current-password" required /></label><button className="primary-btn full-btn">Sign in <ArrowRight size={16} /></button><p className="muted small-note">New here? <button type="button" className="text-link" onClick={() => setDialog("register")}>Create an account</button></p></form>}
        {dialog === "register" && <form onSubmit={register} className="modal-form"><label>Full name<input name="full_name" required minLength={2} placeholder="Your name" /></label><label>Email<input name="email" type="email" autoComplete="email" required placeholder="you@example.org" /></label><label>Password<input name="password" type="password" autoComplete="new-password" minLength={10} required placeholder="At least 10 characters" /></label><label>I'm joining as<select name="role"><option value="volunteer">Volunteer</option><option value="donor">Food donor</option><option value="recipient">Recipient organization</option></select></label><label>Organization name <span className="muted">(for donors and recipients)</span><input name="organization_name" placeholder="Your organization" /></label><div className="form-pair"><label>Organization latitude <span className="muted">(optional)</span><input name="latitude" type="number" step="any" min="-90" max="90" placeholder="12.9716" /></label><label>Organization longitude <span className="muted">(optional)</span><input name="longitude" type="number" step="any" min="-180" max="180" placeholder="77.5946" /></label></div><button className="primary-btn full-btn">Create account <ArrowRight size={16} /></button><p className="muted small-note">Donor and recipient accounts require admin verification.</p></form>}
      </section></div>}
    </div>
  );
}

function ImageAnalysis({ onSuggestion }: { onSuggestion: (value: string) => void }) {
  const [image, setImage] = useState<File | null>(null);
  const [result, setResult] = useState("");
  const [busy, setBusy] = useState(false);
  async function analyze() {
    if (!image) return;
    const data = new FormData();
    data.append("image", image);
    setBusy(true);
    try {
      const suggestion = await api<{ suggested_category: string; estimated_portions: number; confidence_score: number }>("/ai/analyze-image", { method: "POST", body: data });
      setResult(`${suggestion.suggested_category} · about ${suggestion.estimated_portions} portions · ${Math.round(suggestion.confidence_score * 100)}% confidence`);
      onSuggestion(suggestion.suggested_category);
    } catch (e) { setResult(e instanceof Error ? e.message : "Image analysis unavailable."); }
    finally { setBusy(false); }
  }
  return <div className="image-analysis"><label className="upload-field"><ImagePlus size={17} /><span>{image?.name ?? "Add a food photo for AI suggestions"}</span><input type="file" accept="image/*" capture="environment" onChange={(e) => setImage(e.target.files?.[0] ?? null)} /></label>{image && <button type="button" className="text-link" onClick={() => void analyze()} disabled={busy}>{busy ? "Analyzing..." : "Analyze photo"}</button>}{result && <p>{result}</p>}</div>;
}

export default App;
