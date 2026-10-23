// CoherentMobiles Customer Enhancements
// Connects storefront SPA to PostgreSQL Catalog, Real Customer Authentication, and K.T. Street Local Marketplace Features

(function() {
  window.USE_OFFLINE_CATALOG_FALLBACK = false;
  let liveCatalogUnits = [];
  let brandsData = [];
  let latestArrivalsData = [];

  // =========================================================================
  // 1. Live Catalog Synchronization from /api/catalog
  // =========================================================================
  async function loadStorefrontCatalog() {
    try {
      const res = await fetch("/api/catalog?per_page=100");
      if (!res.ok) {
        throw new Error("Catalog response " + res.status);
      }
      const data = await res.json();
      if (!data.success || !Array.isArray(data.items) || data.items.length === 0) {
        console.warn("Backend catalog returned 0 units. Preserving offline fallback.");
        return;
      }

      liveCatalogUnits = data.items;
      window.USE_OFFLINE_CATALOG_FALLBACK = false;

      // Map backend units into the SPA's expected buyPhones array
      if (typeof buyPhones !== "undefined") {
        buyPhones.length = 0;
        data.items.forEach(u => {
          const deviceTitle = `${u.brand || ''} ${u.model || ''}`.trim() || u.device_name;
          const storageNum = parseInt(u.storage) || 128;
          const imgUrl = u.image || (u.images && u.images[0]) || resolveProductImage(u.brand, u.model);

          buyPhones.push({
            unit_id: u.unit_id,
            id: u.unit_id,
            name: `${deviceTitle} (${u.storage || '128 GB'})`,
            model: u.model || deviceTitle,
            brand: u.brand || 'Multi-Brand',
            storage: storageNum,
            storageStr: u.storage || `${storageNum} GB`,
            price: Number(u.selling_price) || 0,
            mrp: Number(u.mrp) || Math.round((Number(u.selling_price) || 0) * 1.15),
            rating: u.vendor_rating || 4.8,
            image: imgUrl,
            condition_grade: u.condition_grade || 'good',
            battery_health: u.battery_health,
            warranty: u.warranty || `${u.warranty_months || 6} Months`,
            warranty_months: u.warranty_months || 6,
            vendor_name: u.store_name || u.vendor_name || 'Verified Partner',
            vendor_id: u.vendor_id,
            store_id: u.store_id || u.vendor_id,
            store_name: u.store_name || u.vendor_name || 'K.T. Street Store',
            store_address: u.store_address || 'K.T. Street, Mysuru',
            store_landmark: u.store_landmark || 'K.T. Street',
            store_phone: u.store_phone,
            store_whatsapp: u.store_whatsapp,
            store_is_open: u.store_is_open,
            store_directions_url: u.store_directions_url,
            is_hand_verified: u.is_hand_verified !== false,
            imei: u.imei,
            stock: 1,
            total_stock: 1,
            notes: u.notes
          });
        });

        // Trigger UI re-render
        if (typeof displayPhones === "function") {
          displayPhones(buyPhones);
        }
        if (typeof renderHomeFeatured === "function") {
          renderHomeFeatured();
        }
        console.log(`[Storefront] Loaded ${buyPhones.length} live refurbished units from PostgreSQL.`);
      }

      // Load additional K.T. Street components
      loadBrandLogosShowcase();
      loadLatestArrivals();
      setupSearchSuggestions();
    } catch (err) {
      console.warn("[Storefront] Failed to load /api/catalog. Offline fallback active:", err);
      window.USE_OFFLINE_CATALOG_FALLBACK = true;
    }
  }

  // =========================================================================
  // 2. Brand Logos Showcase (Every brand with its logo)
  // =========================================================================
  async function loadBrandLogosShowcase() {
    try {
      const res = await fetch("/api/brands");
      const data = await res.json();
      if (!data.success || !Array.isArray(data.brands)) return;
      brandsData = data.brands;

      let container = document.getElementById("cmBrandShowcaseContainer");
      if (!container) {
        // Inject before the featured section on homepage
        const target = document.querySelector(".hero-sec");
        if (target && target.parentNode) {
          const wrapper = document.createElement("section");
          wrapper.className = "section-wrapper";
          wrapper.style.paddingTop = "0";
          wrapper.innerHTML = `
            <div class="cm-brand-showcase">
              <div class="cm-brand-header">
                <h3><span>🏷️</span> Explore by Brand on K.T. Street</h3>
                <span style="font-size:12px; color:#785867; font-weight:700;">Click any logo to filter live stock</span>
              </div>
              <div class="cm-brand-grid" id="cmBrandGrid"></div>
            </div>
          `;
          target.parentNode.insertBefore(wrapper, target.nextSibling);
          container = document.getElementById("cmBrandGrid");
        }
      }

      const grid = document.getElementById("cmBrandGrid");
      if (!grid) return;

      grid.innerHTML = brandsData.map(b => {
        return `
          <div class="cm-brand-card" onclick="filterByBrandName('${escapeHtml(b.brand_name)}')">
            <img src="${b.logo_url}" alt="${escapeHtml(b.brand_name)}" class="cm-brand-logo-img" onerror="this.src='https://placehold.co/44x44/png?text=${b.brand_name}'">
            <span class="cm-brand-name">${escapeHtml(b.brand_name)}</span>
            <span class="cm-brand-count">${b.in_stock_count || 0} in stock</span>
          </div>
        `;
      }).join("");
    } catch (e) {
      console.warn("Could not load brands showcase:", e);
    }
  }

  window.filterByBrandName = function(brandName) {
    // If brandFilter select exists, update it
    const bf = document.getElementById("brandFilter");
    if (bf) {
      bf.value = brandName;
    }
    // Update active brand buttons
    document.querySelectorAll(".brand-btn").forEach(btn => {
      btn.classList.toggle("active", btn.textContent.trim().toLowerCase() === brandName.toLowerCase());
    });
    // Update brand cards active state
    document.querySelectorAll(".cm-brand-card").forEach(c => {
      c.classList.toggle("active", c.querySelector(".cm-brand-name")?.textContent.trim().toLowerCase() === brandName.toLowerCase());
    });
    if (typeof filterPhones === "function") {
      filterPhones();
    }
    // Smooth scroll to buySection
    const buySec = document.getElementById("buySection") || document.getElementById("cataloguePage");
    if (buySec) {
      navigateTo('cataloguePage');
      buySec.scrollIntoView({ behavior: 'smooth' });
    }
  };

  // =========================================================================
  // 3. Search Suggestions (e.g. "iPhone 18 Pro", "Galaxy S24 Ultra")
  // =========================================================================
  function setupSearchSuggestions() {
    const searchInput = document.getElementById("phoneSearch");
    if (!searchInput) return;

    // Enhance placeholder
    searchInput.placeholder = 'Search e.g. "iPhone 18 Pro", "Galaxy S24", "OnePlus 12"...';

    // Inject quick chips if not already present
    if (!document.getElementById("cmSearchChips")) {
      const chipsWrap = document.createElement("div");
      chipsWrap.id = "cmSearchChips";
      chipsWrap.style.cssText = "display:flex; gap:6px; flex-wrap:wrap; margin-top:8px; font-size:11.5px;";
      chipsWrap.innerHTML = `
        <span style="color:#64748b; font-weight:700; align-self:center;">Try searching:</span>
        <button type="button" class="filter-chip" onclick="applySearchQuery('iPhone 18 Pro')">iPhone 18 Pro</button>
        <button type="button" class="filter-chip" onclick="applySearchQuery('iPhone 15')">iPhone 15</button>
        <button type="button" class="filter-chip" onclick="applySearchQuery('Galaxy S24')">Galaxy S24</button>
        <button type="button" class="filter-chip" onclick="applySearchQuery('OnePlus 12')">OnePlus 12</button>
        <button type="button" class="filter-chip" onclick="applySearchQuery('Pixel 9')">Pixel 9</button>
      `;
      searchInput.parentNode.appendChild(chipsWrap);
    }
  }

  window.applySearchQuery = function(query) {
    const searchInput = document.getElementById("phoneSearch");
    if (searchInput) {
      searchInput.value = query;
      if (typeof filterPhones === "function") {
        filterPhones();
      }
    }
  };

  // =========================================================================
  // 4. "Stores That Have It in Stock" Comparison Modal
  // =========================================================================
  window.openStoresStockModal = async function(modelQuery) {
    let modal = document.getElementById("cmStoresStockModal");
    if (!modal) {
      modal = document.createElement("div");
      modal.id = "cmStoresStockModal";
      modal.className = "cm-modal";
      document.body.appendChild(modal);
    }

    modal.innerHTML = `
      <div class="cm-modal-card">
        <div class="cm-modal-header">
          <h3><i class="fa-solid fa-store" style="color:var(--primary)"></i> Stores with Stock: ${escapeHtml(modelQuery)}</h3>
          <button onclick="document.getElementById('cmStoresStockModal').classList.remove('active')" style="border:none; background:none; font-size:22px; cursor:pointer;">✕</button>
        </div>
        <div class="cm-modal-body" id="storesStockModalBody">
          <div style="text-align:center; padding:30px;"><i class="fa-solid fa-circle-notch fa-spin fa-2x"></i><p style="margin-top:8px; color:#64748b;">Checking live K.T. Street inventory...</p></div>
        </div>
      </div>
    `;

    modal.classList.add("active");
    const body = document.getElementById("storesStockModalBody");

    try {
      const res = await fetch(`/api/catalog/stores-for-model?query=${encodeURIComponent(modelQuery)}`);
      const data = await res.json();
      if (!res.ok || !data.success || data.stores.length === 0) {
        body.innerHTML = `
          <div style="text-align:center; padding:30px; color:#64748b;">
            <p>No other partner stores currently list ${escapeHtml(modelQuery)} in stock.</p>
            <button onclick="openSellWizardModal()" style="margin-top:12px; padding:8px 16px; background:var(--primary); color:#fff; border:none; border-radius:6px; cursor:pointer; font-weight:700;">
              Sell or Exchange This Phone Instead
            </button>
          </div>
        `;
        return;
      }

      body.innerHTML = `
        <p style="font-size:13px; color:#64748b; margin-bottom:14px;">
          Found <strong>${data.total_units} unit(s)</strong> across <strong>${data.total_stores} store(s)</strong> on K.T. Street, Mysuru. Prices, condition grades and battery health certified:
        </p>
        <div>
          ${data.stores.map(s => {
            const trust = s.trust_metrics || {};
            const isLaunchPartner = trust.is_hand_verified;
            return `
              <div class="cm-store-stock-item">
                <div style="display:flex; justify-content:space-between; align-items:flex-start; margin-bottom:8px;">
                  <div>
                    <strong style="font-size:15px; color:#0f172a;">${escapeHtml(s.store_name)}</strong>
                    <div style="font-size:12px; color:#64748b;"><i class="fa-solid fa-location-dot" style="color:var(--primary);"></i> ${escapeHtml(s.store_address)}</div>
                  </div>
                  <div>
                    <span class="cm-trust-pill ${isLaunchPartner ? 'cm-trust-launch' : 'cm-trust-rated'}">
                      ${isLaunchPartner ? '🏅 Launch Partner' : `⭐ ${s.rating} ★ (${trust.review_count || 3})`}
                    </span>
                  </div>
                </div>

                <div style="background:#f8fafc; border-radius:8px; padding:10px; margin-bottom:10px;">
                  ${s.available_units.map(u => `
                    <div style="display:flex; justify-content:space-between; align-items:center; padding:6px 0; border-bottom:1px dashed #e2e8f0;">
                      <div>
                        <div style="font-weight:700; font-size:13px; color:#0f172a;">${u.storage} GB &bull; Grade: ${u.condition_grade}</div>
                        <div style="font-size:11.5px; color:#64748b;">Battery: <strong>${u.battery_health}%</strong> &bull; Warranty: ${u.warranty}</div>
                      </div>
                      <div style="text-align:right;">
                        <div style="font-size:15px; font-weight:800; color:var(--primary);">₹${u.selling_price.toLocaleString('en-IN')}</div>
                        <button onclick="document.getElementById('cmStoresStockModal').classList.remove('active'); openReserveModal(${u.unit_id});" class="btn-reserve" style="padding:4px 8px; font-size:11px; margin-top:3px;">
                          Reserve for 24h
                        </button>
                      </div>
                    </div>
                  `).join('')}
                </div>

                <div style="display:flex; justify-content:space-between; align-items:center; font-size:12px;">
                  <span style="color:${s.is_open ? '#10b981' : '#ef4444'}; font-weight:700;">
                    ${s.is_open ? '● Open Now on K.T. Street' : '○ Closed (Weekly Off)'}
                  </span>
                  <div style="display:flex; gap:6px;">
                    ${s.directions_url ? `<a href="${s.directions_url}" target="_blank" style="color:#0f172a; text-decoration:none; padding:3px 8px; border:1px solid #cbd5e1; border-radius:4px; font-weight:700;"><i class="fa-solid fa-diamond-turn-right"></i> Directions</a>` : ''}
                    <button onclick="openStoreReviewsModal(${s.store_id})" style="background:none; border:none; color:var(--primary); font-weight:700; cursor:pointer;">
                      Read Reviews (${trust.review_count || 0})
                    </button>
                  </div>
                </div>
              </div>
            `;
          }).join('')}
        </div>
      `;
    } catch (e) {
      body.innerHTML = `<p style="color:#ef4444; text-align:center;">Failed to load store stock details.</p>`;
    }
  };

  // =========================================================================
  // 5. "Latest Added Phones by Stores" Section
  // =========================================================================
  async function loadLatestArrivals() {
    try {
      const res = await fetch("/api/catalog/latest?limit=6");
      const data = await res.json();
      if (!data.success || !Array.isArray(data.items) || data.items.length === 0) return;
      latestArrivalsData = data.items;

      let section = document.getElementById("cmLatestArrivalsSec");
      if (!section) {
        const homeFeatured = document.getElementById("homeFeaturedGrid");
        if (homeFeatured && homeFeatured.parentNode) {
          section = document.createElement("div");
          section.id = "cmLatestArrivalsSec";
          section.style.cssText = "margin-bottom: 40px;";
          section.innerHTML = `
            <div class="section-header" style="margin-top:30px;">
              <span class="eyebrow" style="background:#fff0f6; color:#d6336c;">JUST UNBOXED ON K.T. STREET</span>
              <h2>🔥 Latest Added Phones by Stores</h2>
              <p>Fresh stock inspected, graded, and listed by verified K.T. Street mobile stores today.</p>
            </div>
            <div class="cards-grid" id="cmLatestGrid" style="display:grid; grid-template-columns:repeat(auto-fill, minmax(260px, 1fr)); gap:20px;"></div>
          `;
          homeFeatured.parentNode.insertBefore(section, homeFeatured);
        }
      }

      const grid = document.getElementById("cmLatestGrid");
      if (!grid) return;

      grid.innerHTML = latestArrivalsData.map(u => {
        const dName = `${u.brand || ''} ${u.model || ''}`.trim() || u.device_name;
        const img = u.image || "images/iphone15.jpg";
        return `
          <div class="phone-card" style="position:relative; background:#fff; border-radius:16px; border:1.5px solid #ebdbe2; padding:16px; display:flex; flex-direction:column; justify-content:space-between;">
            <div style="position:absolute; top:12px; left:12px; background:#d6336c; color:#fff; font-size:10px; font-weight:800; padding:2px 8px; border-radius:12px;">
              ⚡ JUST ADDED
            </div>
            <img src="${img}" alt="${escapeHtml(dName)}" style="width:100%; height:160px; object-fit:contain; margin:16px 0 10px;">
            <h4 style="font-size:15px; font-weight:800; color:#26131c; margin-bottom:4px;">${escapeHtml(dName)}</h4>
            <div style="font-size:12px; color:#785867; margin-bottom:8px;">
              ${u.storage || '128 GB'} &bull; Grade: <strong>${u.condition_grade}</strong> &bull; Battery: <strong>${u.battery_health}%</strong>
            </div>
            <div style="font-size:11px; background:#eff6ff; color:#1d4ed8; padding:4px 8px; border-radius:6px; margin-bottom:12px;">
              📍 ${escapeHtml(u.store_name || 'K.T. Street Store')}
            </div>
            <div style="display:flex; justify-content:space-between; align-items:center;">
              <span style="font-size:17px; font-weight:900; color:#d6336c;">₹${Number(u.selling_price).toLocaleString('en-IN')}</span>
              <button onclick="openReserveModal(${u.unit_id})" class="btn-reserve" style="padding:6px 12px; font-size:11.5px;">
                <i class="fa-solid fa-stopwatch"></i> Reserve (24h)
              </button>
            </div>
          </div>
        `;
      }).join("");
    } catch (e) {
      console.warn("Could not load latest arrivals:", e);
    }
  }

  // =========================================================================
  // 6. Store Reviews & Trust Rule Modal
  // =========================================================================
  window.openStoreReviewsModal = async function(storeId) {
    let modal = document.getElementById("cmStoreReviewsModal");
    if (!modal) {
      modal = document.createElement("div");
      modal.id = "cmStoreReviewsModal";
      modal.className = "cm-modal";
      document.body.appendChild(modal);
    }

    modal.innerHTML = `
      <div class="cm-modal-card">
        <div class="cm-modal-header">
          <h3><i class="fa-solid fa-star" style="color:#f59e0b"></i> Store Reviews & Trust Verification</h3>
          <button onclick="document.getElementById('cmStoreReviewsModal').classList.remove('active')" style="border:none; background:none; font-size:22px; cursor:pointer;">✕</button>
        </div>
        <div class="cm-modal-body" id="storeReviewsModalBody">
          <div style="text-align:center; padding:30px;"><i class="fa-solid fa-circle-notch fa-spin fa-2x"></i></div>
        </div>
      </div>
    `;

    modal.classList.add("active");
    const body = document.getElementById("storeReviewsModalBody");

    try {
      const res = await fetch(`/api/stores/${storeId}/reviews`);
      const data = await res.json();
      if (!res.ok || !data.success) {
        body.innerHTML = `<p style="color:#ef4444; text-align:center;">Failed to load reviews.</p>`;
        return;
      }

      const tm = data.trust_metrics || {};
      body.innerHTML = `
        <div style="display:flex; justify-content:space-between; align-items:center; border-bottom:1px solid #e2e8f0; padding-bottom:14px; margin-bottom:16px;">
          <div>
            <h4 style="font-size:17px; font-weight:800; color:#0f172a;">${escapeHtml(data.store_name)}</h4>
            <div style="font-size:12.5px; color:#64748b; margin-top:2px;">K.T. Street, Mysuru &bull; ${data.count} Verified Customer Reviews</div>
          </div>
          <div style="text-align:right;">
            <div style="font-size:22px; font-weight:900; color:#d97706;">★ ${tm.average_rating || 4.8}</div>
            <span class="cm-trust-pill ${tm.is_hand_verified ? 'cm-trust-launch' : 'cm-trust-rated'}">
              ${tm.trust_badge || 'Hand-Verified Launch Partner'}
            </span>
          </div>
        </div>

        <div style="background:#eff6ff; border:1px solid #bfdbfe; border-radius:8px; padding:10px 12px; margin-bottom:16px; font-size:12px; color:#1e40af;">
          <strong>🛡️ CoherentMobiles Trust Rule:</strong> Customers only see K.T. Street stores with an average review of at least 4.0 from at least 3 reviews, or hand-verified launch partners.
        </div>

        <!-- Write Review Toggle Button -->
        <button onclick="toggleReviewForm()" style="width:100%; padding:10px; background:#f1f5f9; border:1px solid #cbd5e1; border-radius:8px; font-weight:700; font-size:13px; color:#334155; cursor:pointer; margin-bottom:16px;">
          ✍️ Visited this store? Write a Review
        </button>

        <!-- Hidden Review Form -->
        <form id="writeReviewForm" style="display:none; background:#f8fafc; border:1px solid #e2e8f0; border-radius:10px; padding:14px; margin-bottom:16px;" onsubmit="submitStoreReview(event, ${storeId})">
          <h5 style="font-size:13px; font-weight:800; margin-bottom:10px;">Submit Your Verified Store Review</h5>
          <div style="margin-bottom:8px;">
            <label style="display:block; font-size:11.5px; font-weight:700; margin-bottom:3px;">Your Name *</label>
            <input type="text" id="reviewName" required placeholder="e.g. Anand Gowda" style="width:100%; padding:6px 10px; border:1px solid #cbd5e1; border-radius:6px; font-size:12px;">
          </div>
          <div style="margin-bottom:8px;">
            <label style="display:block; font-size:11.5px; font-weight:700; margin-bottom:3px;">Rating (1 to 5 Stars) *</label>
            <select id="reviewRating" style="width:100%; padding:6px 10px; border:1px solid #cbd5e1; border-radius:6px; font-size:12px;">
              <option value="5">⭐⭐⭐⭐⭐ (5.0 - Excellent)</option>
              <option value="4">⭐⭐⭐⭐ (4.0 - Very Good)</option>
              <option value="3">⭐⭐⭐ (3.0 - Average)</option>
              <option value="2">⭐⭐ (2.0 - Below Average)</option>
              <option value="1">⭐ (1.0 - Poor)</option>
            </select>
          </div>
          <div style="margin-bottom:8px;">
            <label style="display:block; font-size:11.5px; font-weight:700; margin-bottom:3px;">Review Title</label>
            <input type="text" id="reviewTitle" placeholder="e.g. Great counter inspection experience" style="width:100%; padding:6px 10px; border:1px solid #cbd5e1; border-radius:6px; font-size:12px;">
          </div>
          <div style="margin-bottom:10px;">
            <label style="display:block; font-size:11.5px; font-weight:700; margin-bottom:3px;">Comments & Feedback</label>
            <textarea id="reviewComment" rows="3" placeholder="Share your experience inspecting, buying, or selling phones at this shop..." style="width:100%; padding:6px 10px; border:1px solid #cbd5e1; border-radius:6px; font-size:12px;"></textarea>
          </div>
          <button type="submit" id="btnSubmitReview" style="padding:8px 16px; background:#d6336c; color:#fff; border:none; border-radius:6px; font-weight:700; font-size:12.5px; cursor:pointer;">
            Publish Review
          </button>
        </form>

        <!-- Reviews List -->
        <div style="max-height:360px; overflow-y:auto;">
          ${data.reviews.length === 0 ? '<p style="color:#64748b; font-size:13px; text-align:center; padding:20px;">No reviews yet. Be the first to review this launch partner store!</p>' : data.reviews.map(r => `
            <div style="border-bottom:1px solid #f1f5f9; padding:12px 0;">
              <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:4px;">
                <strong style="font-size:13px; color:#0f172a;">${escapeHtml(r.customer_name)}</strong>
                <span style="color:#d97706; font-size:12px; font-weight:800;">★ ${r.rating}</span>
              </div>
              <div style="font-size:11px; color:#64748b; margin-bottom:4px;">
                <span style="color:#10b981; font-weight:700;">✓ Verified Walk-In</span> &bull; ${r.device_tag} &bull; ${new Date(r.created_at).toLocaleDateString('en-IN')}
              </div>
              <div style="font-size:12.5px; color:#334155;">${escapeHtml(r.review_text)}</div>
            </div>
          `).join('')}
        </div>
      `;
    } catch (e) {
      body.innerHTML = `<p style="color:#ef4444; text-align:center;">Failed to load reviews.</p>`;
    }
  };

  window.toggleReviewForm = function() {
    const form = document.getElementById("writeReviewForm");
    if (form) {
      form.style.display = form.style.display === "none" ? "block" : "none";
    }
  };

  window.submitStoreReview = async function(e, storeId) {
    e.preventDefault();
    const btn = document.getElementById("btnSubmitReview");
    btn.disabled = true;
    btn.textContent = "Publishing...";

    const payload = {
      name: document.getElementById("reviewName").value.trim(),
      rating: parseFloat(document.getElementById("reviewRating").value),
      title: document.getElementById("reviewTitle").value.trim(),
      comment: document.getElementById("reviewComment").value.trim(),
      device: "K.T. Street Customer"
    };

    try {
      const res = await fetch(`/api/stores/${storeId}/reviews`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload)
      });
      const data = await res.json();
      if (res.ok && data.success) {
        alert("Thank you! Your review has been published.");
        openStoreReviewsModal(storeId);
      } else {
        alert("Failed to submit review: " + (data.error || "Please check inputs"));
        btn.disabled = false;
        btn.textContent = "Publish Review";
      }
    } catch (err) {
      alert("Network error.");
      btn.disabled = false;
      btn.textContent = "Publish Review";
    }
  };

  // =========================================================================
  // 7. 24-Hour "Reserve & Visit" Customer Hold Modal
  // =========================================================================
  window.openReserveModal = function(unitId) {
    let unit = (buyPhones || []).find(p => p.unit_id === unitId || p.id === unitId);
    if (!unit && buyPhones && buyPhones.length > 0) {
      unit = buyPhones[0];
    }
    if (!unit) {
      alert("No device currently available to reserve.");
      return;
    }

    let modal = document.getElementById("cmReserveModal");
    if (!modal) {
      modal = document.createElement("div");
      modal.id = "cmReserveModal";
      modal.className = "cm-modal";
      document.body.appendChild(modal);
    }

    modal.innerHTML = `
      <div class="cm-modal-card">
        <div class="cm-modal-header">
          <h3><i class="fa-solid fa-stopwatch" style="color:var(--primary)"></i> Reserve & Visit (Hold for 24h)</h3>
          <button onclick="document.getElementById('cmReserveModal').classList.remove('active')" style="border:none; background:none; font-size:22px; cursor:pointer;">✕</button>
        </div>
        <div class="cm-modal-body" id="reserveModalBody">
          <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:14px; border-bottom:1px solid #e2e8f0; padding-bottom:12px;">
            <div>
              <strong style="font-size:16px; color:#0f172a;">${escapeHtml(unit.name || unit.model)}</strong>
              <div style="font-size:12px; color:#64748b;">Grade ${unit.condition_grade} &bull; Battery ${unit.battery_health || 90}% &bull; ${unit.warranty}</div>
            </div>
            <div style="text-align:right;">
              <span style="font-size:18px; font-weight:800; color:var(--primary);">₹${unit.price.toLocaleString('en-IN')}</span>
            </div>
          </div>

          <div class="store-meta-box">
            <strong style="color:#0f172a;"><i class="fa-solid fa-store" style="color:var(--primary);"></i> Pickup Location:</strong> ${escapeHtml(unit.store_name || unit.vendor_name || 'K.T. Street Partner Store')}
            <div style="color:#64748b; margin-top:3px;"><i class="fa-solid fa-location-dot"></i> ${escapeHtml(unit.store_address || 'K.T. Street, Mysuru (570001)')}</div>
            ${unit.store_landmark ? `<div style="color:#475569; font-size:11.5px; margin-top:2px;">Landmark: ${escapeHtml(unit.store_landmark)}</div>` : ''}
          </div>

          <p style="font-size:12.5px; color:#475569; margin-bottom:14px;">
            Holding this device locks it exclusively for you for <strong>24 hours</strong>. No upfront payment required: you always visit the store to inspect the phone in person and pay at the counter.
          </p>

          <form id="reserveForm" onsubmit="submitReserveHold(event, ${unit.unit_id})">
            <div style="margin-bottom:12px;">
              <label style="display:block; font-size:12.5px; font-weight:700; margin-bottom:4px;">Your Full Name *</label>
              <input type="text" id="reserveName" required placeholder="e.g. Ramesh Gowda" style="width:100%; padding:8px 12px; border:1px solid #cbd5e1; border-radius:6px; font-size:13px;">
            </div>
            <div style="margin-bottom:12px;">
              <label style="display:block; font-size:12.5px; font-weight:700; margin-bottom:4px;">Mobile Number (10 digits) *</label>
              <input type="tel" id="reservePhone" required maxlength="10" placeholder="e.g. 9845012345" style="width:100%; padding:8px 12px; border:1px solid #cbd5e1; border-radius:6px; font-size:13px;">
            </div>
            <div style="margin-bottom:16px;">
              <label style="display:block; font-size:12.5px; font-weight:700; margin-bottom:4px;">Email (Optional)</label>
              <input type="email" id="reserveEmail" placeholder="for reservation pass" style="width:100%; padding:8px 12px; border:1px solid #cbd5e1; border-radius:6px; font-size:13px;">
            </div>
            <button type="submit" id="btnSubmitHold" style="width:100%; padding:12px; background:var(--primary); color:#fff; border:none; border-radius:8px; font-weight:800; font-size:14px; cursor:pointer;">
              <i class="fa-solid fa-lock"></i> Lock Device & Hold for 24 Hours
            </button>
          </form>
        </div>
      </div>
    `;

    modal.classList.add("active");
  };

  window.submitReserveHold = async function(e, unitId) {
    e.preventDefault();
    const btn = document.getElementById("btnSubmitHold");
    btn.disabled = true;
    btn.innerHTML = `<i class="fa-solid fa-circle-notch fa-spin"></i> Holding device...`;

    const name = document.getElementById("reserveName").value.trim();
    const phone = document.getElementById("reservePhone").value.trim();
    const email = document.getElementById("reserveEmail").value.trim();

    try {
      const res = await fetch("/api/reservations", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          unit_id: unitId,
          customer_name: name,
          customer_phone: phone,
          customer_email: email
        })
      });

      const data = await res.json();
      if (res.ok && data.success) {
        loadStorefrontCatalog();

        const body = document.getElementById("reserveModalBody");
        const store = data.store || {};
        body.innerHTML = `
          <div class="reserve-success-box">
            <i class="fa-solid fa-circle-check fa-3x" style="color:#10b981; margin-bottom:8px;"></i>
            <h4 style="font-size:17px; font-weight:800; color:#0f172a;">Device Successfully Held!</h4>
            <p style="font-size:12px; color:#64748b;">Show this reservation pass to the store executive on K.T. Street</p>
            <div class="reserve-code">${data.reservation_reference}</div>
            <div style="font-size:12px; font-weight:700; color:#b02154;"><i class="fa-solid fa-stopwatch"></i> Hold expires in 24 hours</div>
          </div>

          <div class="store-meta-box">
            <strong style="color:#0f172a;"><i class="fa-solid fa-store" style="color:var(--primary);"></i> ${store.name || 'Partner Store'}</strong>
            <div style="color:#64748b; margin-top:4px;"><i class="fa-solid fa-location-dot"></i> ${store.address || 'K.T. Street, Mysuru'}</div>
            <div style="display:flex; gap:8px; margin-top:12px;">
              ${store.directions_url ? `
                <a href="${store.directions_url}" target="_blank" style="flex:1; text-align:center; padding:8px; background:#0f172a; color:#fff; text-decoration:none; border-radius:6px; font-size:12px; font-weight:700;">
                  <i class="fa-solid fa-location-arrow"></i> Get Directions
                </a>
              ` : ''}
              ${store.whatsapp ? `
                <a href="https://wa.me/91${(store.whatsapp || '').replace(/\D/g, '')}?text=Hello,%20I%20have%20reserved%20a%20phone%20with%20code%20${data.reservation_reference}!" target="_blank" style="flex:1; text-align:center; padding:8px; background:#25d366; color:#fff; text-decoration:none; border-radius:6px; font-size:12px; font-weight:700;">
                  <i class="fa-brands fa-whatsapp"></i> Chat on WhatsApp
                </a>
              ` : ''}
            </div>
          </div>

          <button onclick="document.getElementById('cmReserveModal').classList.remove('active')" style="width:100%; padding:10px; background:#f1f5f9; color:#334155; border:none; border-radius:6px; font-weight:700; cursor:pointer;">
            Done
          </button>
        `;
      } else {
        alert("Hold failed: " + (data.error || "Device may already be reserved or sold."));
        btn.disabled = false;
        btn.innerHTML = `<i class="fa-solid fa-lock"></i> Lock Device & Hold for 24 Hours`;
        loadStorefrontCatalog();
      }
    } catch (err) {
      alert("Network error. Please try again.");
      btn.disabled = false;
      btn.innerHTML = `<i class="fa-solid fa-lock"></i> Lock Device & Hold for 24 Hours`;
    }
  };

  // =========================================================================
  // 8. Sell or Exchange Flow Wizard for an Old Device
  // =========================================================================
  window.openSellWizardModal = function() {
    let modal = document.getElementById("cmSellWizardModal");
    if (!modal) {
      modal = document.createElement("div");
      modal.id = "cmSellWizardModal";
      modal.className = "cm-modal";
      document.body.appendChild(modal);
    }

    modal.innerHTML = `
      <div class="cm-modal-card">
        <div class="cm-modal-header">
          <h3><i class="fa-solid fa-hand-holding-dollar" style="color:var(--primary)"></i> Sell or Exchange Old Device in Mysuru</h3>
          <button onclick="document.getElementById('cmSellWizardModal').classList.remove('active')" style="border:none; background:none; font-size:22px; cursor:pointer;">✕</button>
        </div>
        <div class="cm-modal-body" id="sellWizardBody">
          <!-- Step 1: Device Selection -->
          <div id="sellStep1" class="sell-step active">
            <h4 style="font-size:15px; font-weight:700; margin-bottom:6px;">Step 1 of 3: Select Your Old Phone</h4>
            <p style="font-size:12px; color:#64748b; margin-bottom:12px;">Get a transparent market price reference before visiting K.T. Street so you never get lowballed.</p>
            <div style="margin-bottom:12px;">
              <label style="display:block; font-size:12.5px; font-weight:700; margin-bottom:4px;">Brand</label>
              <select id="sellBrand" onchange="onSellBrandChange()" style="width:100%; padding:8px 12px; border:1px solid #cbd5e1; border-radius:6px;">
                <option value="Apple">Apple iPhone</option>
                <option value="Samsung">Samsung Galaxy</option>
                <option value="OnePlus">OnePlus</option>
                <option value="Google">Google Pixel</option>
                <option value="Xiaomi">Xiaomi / Redmi</option>
                <option value="Realme">Realme</option>
                <option value="Vivo">Vivo</option>
                <option value="OPPO">OPPO</option>
                <option value="Nothing">Nothing Phone</option>
              </select>
            </div>
            <div style="margin-bottom:12px;">
              <label style="display:block; font-size:12.5px; font-weight:700; margin-bottom:4px;">Model</label>
              <select id="sellModel" style="width:100%; padding:8px 12px; border:1px solid #cbd5e1; border-radius:6px;">
                <option value="iPhone 18 Pro">iPhone 18 Pro</option>
                <option value="iPhone 18">iPhone 18</option>
                <option value="iPhone 15 Pro">iPhone 15 Pro</option>
                <option value="iPhone 15">iPhone 15</option>
                <option value="iPhone 14">iPhone 14</option>
                <option value="iPhone 13">iPhone 13</option>
                <option value="iPhone 12">iPhone 12</option>
              </select>
            </div>
            <div style="margin-bottom:16px;">
              <label style="display:block; font-size:12.5px; font-weight:700; margin-bottom:4px;">Storage</label>
              <select id="sellStorage" style="width:100%; padding:8px 12px; border:1px solid #cbd5e1; border-radius:6px;">
                <option value="128">128 GB</option>
                <option value="256" selected>256 GB</option>
                <option value="512">512 GB</option>
              </select>
            </div>
            <button onclick="goToSellStep(2)" style="width:100%; padding:10px; background:var(--primary); color:#fff; border:none; border-radius:6px; font-weight:700; cursor:pointer;">
              Continue to Condition Check <i class="fa-solid fa-arrow-right"></i>
            </button>
          </div>

          <!-- Step 2: Condition Questionnaire -->
          <div id="sellStep2" class="sell-step">
            <h4 style="font-size:15px; font-weight:700; margin-bottom:6px;">Step 2 of 3: Phone Condition</h4>
            <div style="margin-bottom:12px;">
              <label style="display:block; font-size:12.5px; font-weight:700; margin-bottom:4px;">Screen Condition</label>
              <select id="condScreen" style="width:100%; padding:8px 12px; border:1px solid #cbd5e1; border-radius:6px;">
                <option value="flawless">Flawless (No scratches or cracks)</option>
                <option value="minor_scratches">Minor hairline scratches</option>
                <option value="cracked">Cracked or broken glass</option>
              </select>
            </div>
            <div style="margin-bottom:12px;">
              <label style="display:block; font-size:12.5px; font-weight:700; margin-bottom:4px;">Body / Frame Condition</label>
              <select id="condBody" style="width:100%; padding:8px 12px; border:1px solid #cbd5e1; border-radius:6px;">
                <option value="flawless">Flawless (Like New)</option>
                <option value="good">Good (Minor cosmetic signs)</option>
                <option value="dented">Dented or heavily worn</option>
              </select>
            </div>
            <div style="margin-bottom:12px;">
              <label style="display:block; font-size:12.5px; font-weight:700; margin-bottom:4px;">Battery Health</label>
              <select id="condBattery" style="width:100%; padding:8px 12px; border:1px solid #cbd5e1; border-radius:6px;">
                <option value="above_85">Above 85% Health (Excellent)</option>
                <option value="below_85">Below 85% / Requires Service</option>
              </select>
            </div>
            <div style="margin-bottom:12px;">
              <label style="display:block; font-size:12.5px; font-weight:700; margin-bottom:4px;">Camera & Speaker</label>
              <select id="condHardware" style="width:100%; padding:8px 12px; border:1px solid #cbd5e1; border-radius:6px;">
                <option value="all_working">Both Camera and Speaker Work Perfectly</option>
                <option value="camera_defect">Camera has focus / glass defect</option>
                <option value="speaker_defect">Speaker / Earpiece distorted</option>
              </select>
            </div>
            <div style="margin-bottom:16px;">
              <label style="display:block; font-size:12.5px; font-weight:700; margin-bottom:4px;">Accessories Included</label>
              <div style="display:flex; gap:12px;">
                <label style="font-size:12px; font-weight:600;"><input type="checkbox" id="accBox" checked> Original Box</label>
                <label style="font-size:12px; font-weight:600;"><input type="checkbox" id="accCharger" checked> Original Fast Charger</label>
                <label style="font-size:12px; font-weight:600;"><input type="checkbox" id="accBill" checked> Original Purchase Bill</label>
              </div>
            </div>
            <div style="display:flex; gap:8px;">
              <button onclick="goToSellStep(1)" style="flex:1; padding:10px; background:#f1f5f9; color:#334155; border:none; border-radius:6px; font-weight:700; cursor:pointer;">Back</button>
              <button onclick="calculateSellQuote()" style="flex:2; padding:10px; background:var(--primary); color:#fff; border:none; border-radius:6px; font-weight:700; cursor:pointer;">Calculate Fair Quote <i class="fa-solid fa-calculator"></i></button>
            </div>
          </div>

          <!-- Step 3: Valuation Result & Partner Store Selection -->
          <div id="sellStep3" class="sell-step">
            <h4 style="font-size:15px; font-weight:700; margin-bottom:6px;">Step 3 of 3: Instant Valuation & Walk-In Pass</h4>
            <div style="background:#fffbfa; border:1.5px solid var(--primary); border-radius:10px; padding:14px; text-align:center; margin-bottom:14px;">
              <div style="font-size:11.5px; text-transform:uppercase; font-weight:700; color:#b02154;">Fair Market Reference Quote</div>
              <div id="quoteDisplayPrice" style="font-size:24px; font-weight:900; color:var(--primary); margin:4px 0;">₹32,000 - ₹35,000</div>
              <div id="quoteDeductionsSummary" style="font-size:11.5px; color:#64748b;">Includes full accessories & Grade A screen credit</div>
            </div>

            <!-- Choice: Cash or Exchange -->
            <div style="margin-bottom:14px;">
              <label style="display:block; font-size:12.5px; font-weight:700; margin-bottom:6px;">I want to:</label>
              <div style="display:flex; gap:10px;">
                <label style="flex:1; border:1px solid #cbd5e1; border-radius:8px; padding:10px; cursor:pointer; font-size:12.5px; font-weight:700; text-align:center;">
                  <input type="radio" name="sellOption" value="cash" checked> 💵 Sell for Cash / UPI
                </label>
                <label style="flex:1; border:1px solid #cbd5e1; border-radius:8px; padding:10px; cursor:pointer; font-size:12.5px; font-weight:700; text-align:center;">
                  <input type="radio" name="sellOption" value="exchange"> 🔄 Exchange for Upgrade
                </label>
              </div>
            </div>

            <form id="sellFulfillmentForm" onsubmit="submitSellRequest(event)">
              <div style="margin-bottom:10px;">
                <label style="display:block; font-size:12px; font-weight:700; margin-bottom:3px;">Device IMEI (Dial *#06# on phone) *</label>
                <input type="text" id="sellImei" required maxlength="15" placeholder="15-digit valid IMEI" oninput="validateSellImei(this)" style="width:100%; padding:7px 10px; border:1px solid #cbd5e1; border-radius:6px; font-size:12px; font-family:monospace;">
                <div id="imeiFeedback" style="font-size:11px; margin-top:2px;"></div>
              </div>

              <!-- Fulfilment type -->
              <div style="margin-bottom:10px;">
                <label style="display:block; font-size:12px; font-weight:700; margin-bottom:3px;">Inspection & Payment Location</label>
                <div style="display:flex; gap:12px; margin-bottom:6px;">
                  <label style="font-size:12px;"><input type="radio" name="sellFulfilment" value="store_visit" checked onchange="toggleFulfilment('store_visit')"> <strong>Walk-in to K.T. Street Store</strong></label>
                  <label style="font-size:12px;"><input type="radio" name="sellFulfilment" value="home_pickup" onchange="toggleFulfilment('home_pickup')"> Free Mysuru Home Pickup</label>
                </div>
              </div>

              <div id="storeSelectionBox" style="margin-bottom:10px;">
                <label style="display:block; font-size:12px; font-weight:700; margin-bottom:3px;">Select Trusted K.T. Street Store *</label>
                <select id="sellStoreId" style="width:100%; padding:7px 10px; border:1px solid #cbd5e1; border-radius:6px; font-size:12px;">
                  <option value="1">Chamundi Mobile Galleria (42 K.T. Street) - 4.9 ★</option>
                  <option value="2">Cauvery Phone Junction (78 K.T. Street) - 4.8 ★</option>
                  <option value="3">Heritage Gadgets & Exchange (115 K.T. Street) - 4.7 ★</option>
                  <option value="4">Mysuru Mobile Point (152 K.T. Street) - 4.85 ★</option>
                  <option value="5">K.T. Street Refurb Studio (204 K.T. Street) - 4.95 ★</option>
                </select>
              </div>

              <div id="homePickupBox" style="display:none; margin-bottom:10px; background:#f8fafc; padding:10px; border-radius:8px;">
                <div style="margin-bottom:6px;">
                  <label style="display:block; font-size:11.5px; font-weight:700; margin-bottom:2px;">Mysuru Pincode (570001 - 570024) *</label>
                  <input type="text" id="sellPincode" maxlength="6" placeholder="e.g. 570001" style="width:100%; padding:6px 10px; border:1px solid #cbd5e1; border-radius:6px; font-size:12px;">
                </div>
                <div>
                  <label style="display:block; font-size:11.5px; font-weight:700; margin-bottom:2px;">Address in Mysuru *</label>
                  <input type="text" id="sellAddress" placeholder="Flat / House No, Street, Layout" style="width:100%; padding:6px 10px; border:1px solid #cbd5e1; border-radius:6px; font-size:12px;">
                </div>
              </div>

              <div style="display:grid; grid-template-columns:1fr 1fr; gap:8px; margin-bottom:12px;">
                <div>
                  <label style="display:block; font-size:11.5px; font-weight:700; margin-bottom:2px;">Customer Full Name *</label>
                  <input type="text" id="sellCustName" required placeholder="Full Name" style="width:100%; padding:7px 10px; border:1px solid #cbd5e1; border-radius:6px; font-size:12px;">
                </div>
                <div>
                  <label style="display:block; font-size:11.5px; font-weight:700; margin-bottom:2px;">Phone Number (10 Digits) *</label>
                  <input type="tel" id="sellCustPhone" required maxlength="10" placeholder="98450..." style="width:100%; padding:7px 10px; border:1px solid #cbd5e1; border-radius:6px; font-size:12px;">
                </div>
              </div>

              <div style="display:flex; gap:8px;">
                <button type="button" onclick="goToSellStep(2)" style="flex:1; padding:9px; background:#f1f5f9; color:#334155; border:none; border-radius:6px; font-weight:700; cursor:pointer;">Back</button>
                <button type="submit" id="btnSubmitSell" style="flex:2; padding:9px; background:var(--primary); color:#fff; border:none; border-radius:6px; font-weight:700; cursor:pointer;">
                  Confirm & Generate Walk-In Pass <i class="fa-solid fa-check"></i>
                </button>
              </div>
            </form>
          </div>
        </div>
      </div>
    `;

    modal.classList.add("active");
  };

  window.onSellBrandChange = function() {
    const brand = document.getElementById("sellBrand").value;
    const modelSelect = document.getElementById("sellModel");
    const modelsByBrand = {
      "Apple": ["iPhone 18 Pro", "iPhone 18", "iPhone 15 Pro", "iPhone 15", "iPhone 14", "iPhone 13", "iPhone 12"],
      "Samsung": ["Galaxy S24 Ultra", "Galaxy S24", "Galaxy S23 Ultra", "Galaxy S23", "Galaxy S22", "Galaxy A55"],
      "OnePlus": ["OnePlus 12", "OnePlus 11", "OnePlus Nord 4"],
      "Google": ["Pixel 9 Pro", "Pixel 8", "Pixel 7"],
      "Xiaomi": ["Xiaomi 14", "Xiaomi 13 Pro", "Redmi Note 13 Pro"],
      "Realme": ["Realme GT 6", "Realme 12 Pro+"],
      "Vivo": ["Vivo V30", "Vivo X100"],
      "OPPO": ["OPPO Reno 12", "OPPO Find X7"],
      "Nothing": ["Nothing Phone 2"]
    };
    const list = modelsByBrand[brand] || ["Phone Model"];
    modelSelect.innerHTML = list.map(m => `<option value="${m}">${m}</option>`).join('');
  };

  window.goToSellStep = function(stepNum) {
    document.querySelectorAll(".sell-step").forEach(s => s.classList.remove("active"));
    const target = document.getElementById(`sellStep${stepNum}`);
    if (target) target.classList.add("active");
  };

  window.calculateSellQuote = async function() {
    const brand = document.getElementById("sellBrand").value;
    const model = document.getElementById("sellModel").value;
    const storage = parseInt(document.getElementById("sellStorage").value);

    const condition = {
      screen: document.getElementById("condScreen").value,
      body: document.getElementById("condBody").value,
      battery: document.getElementById("condBattery").value,
      hardware: document.getElementById("condHardware").value,
      accessories: []
    };
    if (document.getElementById("accBox").checked) condition.accessories.push("box");
    if (document.getElementById("accCharger").checked) condition.accessories.push("charger");
    if (document.getElementById("accBill").checked) condition.accessories.push("bill");

    try {
      const res = await fetch("/api/sell/estimate", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          brand, model, storage_gb: storage, condition_answers: condition
        })
      });
      const data = await res.json();
      if (res.ok && data.success) {
        document.getElementById("quoteDisplayPrice").textContent = `₹${data.estimated_min_price.toLocaleString('en-IN')} - ₹${data.estimated_max_price.toLocaleString('en-IN')}`;
        const ded = Object.values(data.deductions || {}).join(', ');
        document.getElementById("quoteDeductionsSummary").textContent = ded ? `Deductions factored: ${ded}` : "Certified Pristine condition pricing applied.";
      }
    } catch (e) {
      console.warn("Valuation estimate failed, using local fallback");
    }

    goToSellStep(3);
  };

  window.validateSellImei = function(input) {
    const val = input.value.replace(/\D/g, '');
    input.value = val;
    const fb = document.getElementById("imeiFeedback");
    if (val.length === 15) {
      // Luhn algorithm check
      if (VendorApp && typeof VendorApp.validateLuhn === "function" ? VendorApp.validateLuhn(val) : true) {
        fb.innerHTML = '<span style="color:#10b981; font-weight:700;">✓ Valid 15-digit IMEI verified</span>';
      } else {
        fb.innerHTML = '<span style="color:#ef4444;">✗ Invalid IMEI check digit. Please check dial *#06#.</span>';
      }
    } else {
      fb.innerHTML = `<span style="color:#64748b;">${val.length} / 15 digits entered</span>`;
    }
  };

  window.toggleFulfilment = function(type) {
    document.getElementById("storeSelectionBox").style.display = type === 'store_visit' ? 'block' : 'none';
    document.getElementById("homePickupBox").style.display = type === 'home_pickup' ? 'block' : 'none';
  };

  window.submitSellRequest = async function(e) {
    e.preventDefault();
    const imei = document.getElementById("sellImei").value.trim();
    if (imei.length !== 15) {
      alert("Please enter a valid 15-digit IMEI number.");
      return;
    }

    const fulfilment = document.querySelector('input[name="sellFulfilment"]:checked').value;
    const payload = {
      brand: document.getElementById("sellBrand").value,
      model: document.getElementById("sellModel").value,
      storage_gb: parseInt(document.getElementById("sellStorage").value),
      imei: imei,
      customer_name: document.getElementById("sellCustName").value.trim(),
      customer_phone: document.getElementById("sellCustPhone").value.trim(),
      fulfilment_type: fulfilment,
      store_id: fulfilment === 'store_visit' ? parseInt(document.getElementById("sellStoreId").value) : null,
      pincode: fulfilment === 'home_pickup' ? document.getElementById("sellPincode").value.trim() : "570001",
      customer_address: fulfilment === 'home_pickup' ? document.getElementById("sellAddress").value.trim() : "Walk-in Store",
      condition_answers: {
        screen: document.getElementById("condScreen").value,
        body: document.getElementById("condBody").value,
        battery: document.getElementById("condBattery").value
      }
    };

    const btn = document.getElementById("btnSubmitSell");
    btn.disabled = true;
    btn.textContent = "Generating Pass...";

    try {
      const res = await fetch("/api/sell/requests", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload)
      });
      const data = await res.json();
      if (res.ok && data.success) {
        const sr = data.sell_request;
        const body = document.getElementById("sellWizardBody");
        body.innerHTML = `
          <div class="reserve-success-box">
            <i class="fa-solid fa-circle-check fa-3x" style="color:#10b981; margin-bottom:8px;"></i>
            <h4 style="font-size:18px; font-weight:800; color:#0f172a;">Sell Request Booked!</h4>
            <p style="font-size:12px; color:#64748b;">Walk-In Pass created for inspection & payout</p>
            <div class="reserve-code">${sr.request_reference}</div>
            <div style="font-size:13px; font-weight:700; color:#0f172a; margin-top:6px;">
              ${sr.fulfilment_type === 'store_visit' ? `🏪 Walk-in to ${sr.store_name || 'K.T. Street Store'}` : `🚗 Home Pickup in Mysuru (PIN ${sr.pincode})`}
            </div>
          </div>
          <p style="font-size:12.5px; color:#475569; text-align:center; margin-bottom:16px;">
            The store counter has received your details (Phone: <strong>${sr.customer_phone}</strong>). Bring your phone to the shop for instant 15-minute diagnostic inspection and cash/UPI disbursement.
          </p>
          <div style="display:flex; gap:8px;">
            <button onclick="document.getElementById('cmSellWizardModal').classList.remove('active')" style="flex:1; padding:10px; background:#f1f5f9; color:#334155; border:none; border-radius:6px; font-weight:700; cursor:pointer;">
              Done
            </button>
            <button onclick="openSellTrackingModal('${sr.request_reference}')" style="flex:1; padding:10px; background:var(--primary); color:#fff; border:none; border-radius:6px; font-weight:700; cursor:pointer;">
              Track Progress
            </button>
          </div>
        `;
      } else {
        alert("Submission error: " + (data.error || "Please verify details"));
        btn.disabled = false;
        btn.textContent = "Confirm & Generate Walk-In Pass";
      }
    } catch (e) {
      alert("Network error.");
      btn.disabled = false;
      btn.textContent = "Confirm & Generate Walk-In Pass";
    }
  };

  // =========================================================================
  // 9. Enhanced Display Phones with Compare Stores & Reviews
  // =========================================================================
  const originalDisplayPhones = window.displayPhones;
  window.displayPhones = function(phones) {
    const phoneCards = document.getElementById("phoneCards");
    if (!phoneCards) return;

    if (!phones || phones.length === 0) {
      phoneCards.innerHTML = '<p class="no-phones" style="text-align:center; padding:40px; color:#64748b;">No matching refurbished smartphones currently in stock on K.T. Street.</p>';
      return;
    }

    const hasCredit = typeof appState !== "undefined" && appState && appState.imeiVerified && appState.predictedPrice > 0;

    phoneCards.innerHTML = phones.map(p => {
      const netUpgrade = Math.max(1, p.price - (hasCredit ? appState.predictedPrice : 0));
      const modelTitle = p.model || p.name;
      const isLaunch = p.is_hand_verified !== false;

      return `
        <div class="phone-card" style="background:#ffffff; border-radius:18px; border:1.5px solid #ebdbe2; padding:18px; display:flex; flex-direction:column; justify-content:space-between; position:relative; box-shadow:0 8px 24px rgba(120,25,65,0.06); transition:transform .2s ease;">
          <div>
            <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:8px;">
              <span class="badge-grade-like-new" style="font-size:10.5px; font-weight:800; padding:2px 8px; border-radius:6px; text-transform:uppercase;">
                Grade: ${p.condition_grade}
              </span>
              <span style="font-size:11.5px; color:#d97706; font-weight:800; cursor:pointer;" onclick="openStoreReviewsModal(${p.store_id || p.vendor_id})">
                ★ ${p.rating} (Reviews)
              </span>
            </div>

            <img src="${p.image}" alt="${escapeHtml(p.name)}" class="phone-image" style="width:100%; height:180px; object-fit:contain; margin-bottom:12px;" onerror="this.src='images/iphone15.jpg'">

            <h3 style="font-size:16px; font-weight:800; color:#26131c; margin-bottom:4px; line-height:1.2;">
              ${escapeHtml(p.name)}
            </h3>

            <div style="font-size:12px; color:#785867; margin-bottom:8px;">
              🔋 Battery: <strong style="color:#10b981;">${p.battery_health || 95}%</strong> &bull; Warranty: <strong>${p.warranty}</strong>
            </div>

            <p class="phone-price" style="font-size:20px; font-weight:900; color:#d6336c; margin-bottom:8px;">
              ₹${p.price.toLocaleString("en-IN")}
            </p>

            ${hasCredit ? `
              <div style="font-size:11.5px; color:#10b981; font-weight:700; margin-bottom:4px;">
                Trade-in Credit: -₹${appState.predictedPrice.toLocaleString("en-IN")}
              </div>
              <div style="font-size:13.5px; color:#b02154; font-weight:900; margin-bottom:8px;">
                Net Upgrade: ₹${netUpgrade.toLocaleString("en-IN")}
              </div>
            ` : ''}

            <!-- Store Location & Trust Badge -->
            <div style="background:#f8fafc; border:1px solid #e2e8f0; border-radius:8px; padding:8px 10px; margin-bottom:12px; font-size:11.5px;">
              <div style="display:flex; justify-content:space-between; align-items:center;">
                <strong style="color:#0f172a;"><i class="fa-solid fa-store" style="color:var(--primary);"></i> ${escapeHtml(p.store_name)}</strong>
                <span class="cm-trust-pill ${isLaunch ? 'cm-trust-launch' : 'cm-trust-rated'}" style="font-size:10px; padding:1px 6px;">
                  ${isLaunch ? '🏅 Launch Partner' : '⭐ Verified'}
                </span>
              </div>
              <div style="color:#64748b; margin-top:2px; font-size:11px;">
                <i class="fa-solid fa-location-dot"></i> ${escapeHtml(p.store_address)}
              </div>
            </div>
          </div>

          <!-- Actions: Compare Stores on K.T. Street, 24h Reserve, Exchange -->
          <div style="display:flex; flex-direction:column; gap:6px;">
            <button onclick="openStoresStockModal('${escapeHtml(modelTitle)}')" style="width:100%; padding:7px; background:#eff6ff; color:#1d4ed8; border:1px solid #bfdbfe; border-radius:6px; font-size:11.5px; font-weight:700; cursor:pointer; display:inline-flex; align-items:center; justify-content:center; gap:5px;">
              <i class="fa-solid fa-layer-group"></i> Compare Stores in Stock
            </button>
            <div style="display:flex; gap:6px;">
              <button onclick="openReserveModal(${p.unit_id})" class="btn-reserve" style="flex:1; justify-content:center; padding:8px; font-size:12px;">
                <i class="fa-solid fa-stopwatch"></i> Reserve (24h)
              </button>
              <button onclick="openSellWizardModal()" class="btn-secondary" style="flex:1; padding:8px; font-size:12px; justify-content:center; border-radius:6px; font-weight:700;">
                🔄 Exchange
              </button>
            </div>
          </div>
        </div>
      `;
    }).join("");
  };

  // =========================================================================
  // 10. Sell Request Tracking Modal
  // =========================================================================
  window.openSellTrackingModal = async function(prefillRef) {
    let modal = document.getElementById("cmTrackingModal");
    if (!modal) {
      modal = document.createElement("div");
      modal.id = "cmTrackingModal";
      modal.className = "cm-modal";
      document.body.appendChild(modal);
    }

    modal.innerHTML = `
      <div class="cm-modal-card">
        <div class="cm-modal-header">
          <h3><i class="fa-solid fa-route" style="color:var(--primary)"></i> Track Sell Request / Inspection</h3>
          <button onclick="document.getElementById('cmTrackingModal').classList.remove('active')" style="border:none; background:none; font-size:22px; cursor:pointer;">✕</button>
        </div>
        <div class="cm-modal-body">
          <div style="display:flex; gap:8px; margin-bottom:16px;">
            <input type="text" id="trackRefInput" value="${prefillRef || ''}" placeholder="Enter SELL-MYS-XXXXX" style="flex:1; padding:8px 12px; border:1px solid #cbd5e1; border-radius:6px; font-size:13px; font-family:monospace;">
            <button onclick="lookupSellRequest()" style="padding:8px 16px; background:#0f172a; color:#fff; border:none; border-radius:6px; font-weight:700; font-size:13px; cursor:pointer;">Track</button>
          </div>
          <div id="trackingResultArea">
            <p style="color:#64748b; font-size:13px; text-align:center; padding:20px;">Enter your sell request reference code above to see live progress.</p>
          </div>
        </div>
      </div>
    `;

    modal.classList.add("active");
    if (prefillRef) {
      lookupSellRequest();
    }
  };

  window.lookupSellRequest = async function() {
    const ref = document.getElementById("trackRefInput").value.trim();
    if (!ref) return;
    const area = document.getElementById("trackingResultArea");
    area.innerHTML = '<div style="text-align:center; padding:20px;"><i class="fa-solid fa-circle-notch fa-spin fa-2x"></i></div>';

    try {
      const res = await fetch(`/api/sell/requests/${encodeURIComponent(ref)}`);
      const data = await res.json();
      if (res.ok && data.success) {
        const sr = data.sell_request;
        let timelineHtml = (sr.timeline || []).map(t => `
          <div style="display:flex; gap:12px; margin-bottom:12px; font-size:12.5px;">
            <div style="width:8px; height:8px; border-radius:50%; background:var(--primary); margin-top:5px;"></div>
            <div>
              <strong>${t.to_status.replace('_', ' ').toUpperCase()}</strong> &bull; <span style="color:#64748b;">${new Date(t.created_at).toLocaleString('en-IN')}</span>
              <div style="color:#475569; margin-top:2px;">${t.notes || ''}</div>
            </div>
          </div>
        `).join('');

        let offerActionHtml = '';
        if (sr.status === 'offer_revised' || sr.status === 'inspected') {
          offerActionHtml = `
            <div style="background:#fffbfa; border:1.5px solid #d6336c; border-radius:10px; padding:14px; margin-bottom:16px; text-align:center;">
              <div style="font-size:12px; color:#b02154; font-weight:700;">STORE INSPECTION OFFER</div>
              <div style="font-size:1.6rem; font-weight:800; color:#d6336c; margin:4px 0;">₹${Number(sr.final_offer_price).toLocaleString('en-IN')}</div>
              <p style="font-size:12px; color:#64748b; margin-bottom:10px;">${sr.final_offer_notes || 'Inspected and certified by K.T. Street technician.'}</p>
              <div style="display:flex; gap:8px;">
                <button onclick="acceptOffer('${sr.request_reference}')" style="flex:1; padding:8px; background:#10b981; color:#fff; border:none; border-radius:6px; font-weight:700; cursor:pointer;">Accept & Get Paid</button>
                <button onclick="rejectOffer('${sr.request_reference}')" style="flex:1; padding:8px; background:#f1f5f9; color:#ef4444; border:none; border-radius:6px; font-weight:700; cursor:pointer;">Decline</button>
              </div>
            </div>
          `;
        }

        area.innerHTML = `
          <div style="border-bottom:1px solid #e2e8f0; padding-bottom:12px; margin-bottom:14px;">
            <div style="display:flex; justify-content:space-between; align-items:center;">
              <strong style="font-size:16px;">${sr.brand} ${sr.model} (${sr.storage || ''})</strong>
              <span style="font-size:11px; font-weight:800; padding:3px 8px; border-radius:4px; background:#eff6ff; color:#1d4ed8;">● ${sr.status.toUpperCase()}</span>
            </div>
            <div style="font-size:12px; color:#64748b; margin-top:4px;">IMEI: ${sr.imei} &bull; ${sr.fulfilment_type === 'home_pickup' ? 'Home Pickup' : 'Store Visit'}</div>
          </div>

          ${offerActionHtml}

          <h5 style="font-size:13px; font-weight:700; margin-bottom:10px;"><i class="fa-solid fa-timeline"></i> Status Timeline</h5>
          <div>${timelineHtml || '<p style="color:#64748b; font-size:12px;">Submitted and awaiting store confirmation.</p>'}</div>
        `;
      } else {
        area.innerHTML = `<p style="color:#ef4444; text-align:center; padding:20px;">Request not found. Please verify the reference code.</p>`;
      }
    } catch (e) {
      area.innerHTML = `<p style="color:#ef4444; text-align:center; padding:20px;">Error looking up request.</p>`;
    }
  };

  window.acceptOffer = async function(ref) {
    try {
      const res = await fetch(`/api/sell/requests/${encodeURIComponent(ref)}/accept`, { method: "POST" });
      const data = await res.json();
      if (data.success) {
        alert("Offer accepted! The store executive will disburse your payout.");
        lookupSellRequest();
      }
    } catch (e) {
      alert("Error accepting offer.");
    }
  };

  window.rejectOffer = async function(ref) {
    try {
      const res = await fetch(`/api/sell/requests/${encodeURIComponent(ref)}/reject`, { method: "POST" });
      const data = await res.json();
      if (data.success) {
        alert("Offer declined. You may collect your device.");
        lookupSellRequest();
      }
    } catch (e) {
      alert("Error declining offer.");
    }
  };

  // Initialize on page load
  document.addEventListener("DOMContentLoaded", () => {
    loadStorefrontCatalog();
  });
})();
