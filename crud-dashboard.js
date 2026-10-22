/**
 * CoherentMobiles - Enterprise Admin & Vendor Dashboard Controller
 * Modern SaaS frontend controller connected to Flask + Redis backend.
 * Provides complete Vendor management, Products List CRUD, dynamic analytics & telemetry.
 */

(function () {
  'use strict';

  // =========================================================================
  // 1. BACKEND API CONFIGURATION & CONNECTION STATE
  // =========================================================================
  const API_BASE_URL = (typeof window !== 'undefined' && window.location && window.location.origin && window.location.origin.includes(':5000'))
    ? '/api'
    : 'http://localhost:5000/api';

  // Application State
  const state = {
    isBackendLive: false,
    activeView: 'vendors',      // 'vendors', 'overview', 'products', 'categories', 'inventory', 'orders', 'analytics', 'settings'
    products: [],               // Full product catalogue from Redis
    filteredProducts: [],       // Products after search/filters
    vendors: [],                // Registered vendor partners
    activeVendorFilter: null,   // null (all) or vendor ID
    stats: null,                // Dynamic portfolio metrics from backend
    searchQuery: '',
    brandFilter: '',
    statusFilter: '',
    sortBy: 'id-asc',
    viewMode: 'table',          // 'table' or 'cards'
    pagination: {
      currentPage: 1,
      pageSize: 10,
      totalPages: 1
    },
    editingProductId: null,
    deletingProductId: null
  };

  // Image resolution fallback helper
  function resolveImage(brand, model) {
    const s = `${brand || ''} ${model || ''}`.toLowerCase();
    if (s.includes('iphone 15 pro')) return 'images/iphone15pro.jpg';
    if (s.includes('iphone') || s.includes('apple')) return 'images/iphone15.jpg';
    if (s.includes('a55')) return 'images/galaxy-a55.jpg';
    if (s.includes('galaxy') || s.includes('s24') || s.includes('samsung')) return 'images/galaxy-s24.jpg';
    if (s.includes('nord')) return 'images/oneplus-nord4.jpg';
    if (s.includes('oneplus')) return 'images/oneplus12.jpg';
    if (s.includes('redmi')) return 'images/redmi-note-13-pro.jpg';
    if (s.includes('xiaomi')) return 'images/xiaomi14.jpg';
    if (s.includes('realme')) return 'images/realme-gt6.jpg';
    if (s.includes('vivo')) return 'images/vivo-v30.jpg';
    if (s.includes('oppo')) return 'images/oppo-reno12.jpg';
    return 'images/iphone15.jpg';
  }

  // Format currency in Indian Rupees (e.g. ₹1,29,999)
  function formatINR(val) {
    const num = Number(val);
    if (isNaN(num)) return '₹0';
    try {
      return new Intl.NumberFormat('en-IN', {
        style: 'currency',
        currency: 'INR',
        maximumFractionDigits: 0
      }).format(num);
    } catch (e) {
      return '₹' + Math.round(num).toLocaleString('en-IN');
    }
  }

  // Format date helper
  function formatDate(isoStr) {
    if (!isoStr) return 'Recently';
    try {
      const d = new Date(isoStr);
      if (isNaN(d.getTime())) return isoStr;
      return d.toLocaleDateString('en-IN', {
        month: 'short',
        day: 'numeric',
        year: 'numeric'
      });
    } catch (e) {
      return isoStr;
    }
  }

  // =========================================================================
  // 2. BACKEND API SERVICE (Strict Backend Connection - No silent localStorage)
  // =========================================================================
  const ApiService = {
    // Health check
    async checkHealth() {
      try {
        const controller = new AbortController();
        const timeout = setTimeout(() => controller.abort(), 3000);
        const res = await fetch(`${API_BASE_URL}/health`, {
          method: 'GET',
          mode: 'cors',
          signal: controller.signal
        });
        clearTimeout(timeout);
        if (res.ok) {
          const data = await res.json();
          return data.redis_connected === true;
        }
        return false;
      } catch (err) {
        return false;
      }
    },

    // Fetch all products
    async getProducts(params = {}) {
      const query = new URLSearchParams();
      if (params.vendor_id) query.append('vendor_id', params.vendor_id);
      if (params.brand) query.append('brand', params.brand);
      if (params.status) query.append('status', params.status);
      if (params.search) query.append('search', params.search);
      if (params.sort) query.append('sort', params.sort);

      const qs = query.toString() ? `?${query.toString()}` : '';
      const res = await fetch(`${API_BASE_URL}/mobiles${qs}`, { method: 'GET', mode: 'cors' });
      if (!res.ok) {
        const errJson = await res.json().catch(() => ({}));
        throw new Error(errJson.error || `Failed to fetch products (HTTP ${res.status})`);
      }
      return await res.json();
    },

    // Get product by ID
    async getProductById(id) {
      const res = await fetch(`${API_BASE_URL}/mobiles/${id}`, { method: 'GET', mode: 'cors' });
      if (!res.ok) {
        const errJson = await res.json().catch(() => ({}));
        throw new Error(errJson.error || `Product #${id} not found`);
      }
      return await res.json();
    },

    // Create new product
    async createProduct(productData) {
      const res = await fetch(`${API_BASE_URL}/mobiles`, {
        method: 'POST',
        mode: 'cors',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(productData)
      });
      const data = await res.json().catch(() => ({}));
      if (!res.ok) {
        throw new Error(data.error || 'Failed to create product');
      }
      return data.mobile;
    },

    // Update existing product
    async updateProduct(id, productData) {
      const res = await fetch(`${API_BASE_URL}/mobiles/${id}`, {
        method: 'PUT',
        mode: 'cors',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(productData)
      });
      const data = await res.json().catch(() => ({}));
      if (!res.ok) {
        throw new Error(data.error || 'Failed to update product');
      }
      return data.mobile;
    },

    // Delete product
    async deleteProduct(id) {
      const res = await fetch(`${API_BASE_URL}/mobiles/${id}`, {
        method: 'DELETE',
        mode: 'cors'
      });
      const data = await res.json().catch(() => ({}));
      if (!res.ok) {
        throw new Error(data.error || 'Failed to delete product');
      }
      return true;
    },

    // Fetch vendors
    async getVendors() {
      const res = await fetch(`${API_BASE_URL}/vendors`, { method: 'GET', mode: 'cors' });
      if (!res.ok) {
        const errJson = await res.json().catch(() => ({}));
        throw new Error(errJson.error || 'Failed to fetch vendors');
      }
      return await res.json();
    },

    // Create vendor
    async createVendor(vendorData) {
      const res = await fetch(`${API_BASE_URL}/vendors`, {
        method: 'POST',
        mode: 'cors',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(vendorData)
      });
      const data = await res.json().catch(() => ({}));
      if (!res.ok) {
        throw new Error(data.error || 'Failed to create vendor');
      }
      return data.vendor;
    },

    // Fetch dynamic statistics
    async getStats() {
      const res = await fetch(`${API_BASE_URL}/stats`, { method: 'GET', mode: 'cors' });
      if (!res.ok) {
        const errJson = await res.json().catch(() => ({}));
        throw new Error(errJson.error || 'Failed to fetch stats');
      }
      const data = await res.json();
      return data.stats;
    },

    // Reset Redis dataset to sample data
    async resetData() {
      const res = await fetch(`${API_BASE_URL}/reset`, {
        method: 'POST',
        mode: 'cors'
      });
      const data = await res.json().catch(() => ({}));
      if (!res.ok) {
        throw new Error(data.error || 'Failed to reset dataset');
      }
      return data.mobiles;
    }
  };

  // =========================================================================
  // 3. DOM ELEMENTS CACHE
  // =========================================================================
  const dom = {
    // Sidebar & layout
    dashSidebar: document.getElementById('dashSidebar'),
    btnToggleSidebar: document.getElementById('btnToggleSidebar'),
    sidebarBackdrop: document.getElementById('sidebarBackdrop'),
    navLinks: document.querySelectorAll('.sidebar-nav .nav-link[data-view]'),
    navProductCount: document.getElementById('navProductCount'),
    navVendorCount: document.getElementById('navVendorCount'),
    dataModeBadge: document.getElementById('dataModeBadge'),
    dataModeLabel: document.getElementById('dataModeLabel'),

    // Topbar
    topbarTitle: document.getElementById('topbarTitle'),
    topbarBreadcrumb: document.getElementById('topbarBreadcrumb'),
    topbarSearchInput: document.getElementById('topbarSearchInput'),
    notifBellBtn: document.getElementById('notifBellBtn'),
    notifDropdown: document.getElementById('notifDropdown'),
    backendAlertBanner: document.getElementById('backendAlertBanner'),
    btnBannerRetry: document.getElementById('btnBannerRetry'),
    btnOpenAddModal: document.getElementById('btnOpenAddModal'),

    // Views
    views: document.querySelectorAll('.dashboard-view'),

    // Vendor View & Summary Cards
    statVendorTotal: document.getElementById('statVendorTotal'),
    statTotalProducts: document.getElementById('statTotalProducts'),
    statInStockCount: document.getElementById('statInStockCount'),
    statOutOfStockCount: document.getElementById('statOutOfStockCount'),
    statTotalValue: document.getElementById('statTotalValue'),
    statInStockPct: document.getElementById('statInStockPct'),
    vendorPillsBar: document.getElementById('vendorPillsBar'),
    selectedVendorStrip: document.getElementById('selectedVendorStrip'),
    stripVendorName: document.getElementById('stripVendorName'),
    stripVendorCode: document.getElementById('stripVendorCode'),
    stripVendorEmail: document.getElementById('stripVendorEmail'),
    stripVendorPhone: document.getElementById('stripVendorPhone'),
    stripVendorLocation: document.getElementById('stripVendorLocation'),
    stripVendorRating: document.getElementById('stripVendorRating'),
    stripVendorProductCount: document.getElementById('stripVendorProductCount'),
    btnClearVendorFilter: document.getElementById('btnClearVendorFilter'),
    btnOpenAddVendorModal: document.getElementById('btnOpenAddVendorModal'),

    // Table & Controls
    recordsBadge: document.getElementById('recordsBadge'),
    tableSearchInput: document.getElementById('tableSearchInput'),
    btnClearSearch: document.getElementById('btnClearSearch'),
    brandSelectFilter: document.getElementById('brandSelectFilter'),
    statusSelectFilter: document.getElementById('statusSelectFilter'),
    sortSelectFilter: document.getElementById('sortSelectFilter'),
    btnViewTable: document.getElementById('btnViewTable'),
    btnViewCards: document.getElementById('btnViewCards'),
    btnExportCSV: document.getElementById('btnExportCSV'),
    btnRefresh: document.getElementById('btnRefresh'),
    refreshIcon: document.getElementById('refreshIcon'),
    btnOpenAddModalToolbar: document.getElementById('btnOpenAddModalToolbar'),
    brandPillsBar: document.getElementById('brandPillsBar'),
    tableContainer: document.getElementById('tableContainer'),
    inventoryTable: document.getElementById('inventoryTable'),
    inventoryTableBody: document.getElementById('inventoryTableBody'),
    cardsGridView: document.getElementById('cardsGridView'),
    emptyState: document.getElementById('emptyState'),
    btnEmptyResetFilters: document.getElementById('btnEmptyResetFilters'),
    btnEmptyAdd: document.getElementById('btnEmptyAdd'),
    showingCountText: document.getElementById('showingCountText'),
    totalCountText: document.getElementById('totalCountText'),
    pageSizeSelect: document.getElementById('pageSizeSelect'),
    btnPrevPage: document.getElementById('btnPrevPage'),
    btnNextPage: document.getElementById('btnNextPage'),
    pageIndicator: document.getElementById('pageIndicator'),
    btnResetData: document.getElementById('btnResetData'),

    // Overview View
    ovAvgPrice: document.getElementById('ovAvgPrice'),
    ovFlagshipCount: document.getElementById('ovFlagshipCount'),
    ovStockHealth: document.getElementById('ovStockHealth'),
    ovVendorCount: document.getElementById('ovVendorCount'),
    brandStatsGrid: document.getElementById('brandStatsGrid'),
    topExpensiveList: document.getElementById('topExpensiveList'),
    activityFeed: document.getElementById('activityFeed'),
    btnGoToAnalytics: document.getElementById('btnGoToAnalytics'),

    // Categories & Inventory Views
    categoriesGrid: document.getElementById('categoriesGrid'),
    inventoryStatusSummary: document.getElementById('inventoryStatusSummary'),
    analyticsDetailContainer: document.getElementById('analyticsDetailContainer'),

    // Settings View
    settingsRedisStatus: document.getElementById('settingsRedisStatus'),
    settingsRedisHost: document.getElementById('settingsRedisHost'),

    // Add Product Modal
    addMobileModalOverlay: document.getElementById('addMobileModalOverlay'),
    btnCloseAddModal: document.getElementById('btnCloseAddModal'),
    btnCancelAddModal: document.getElementById('btnCancelAddModal'),
    addMobileForm: document.getElementById('addMobileForm'),
    addModalAlert: document.getElementById('addModalAlert'),
    addBrandInput: document.getElementById('addBrandInput'),
    addModelInput: document.getElementById('addModelInput'),
    addPriceInput: document.getElementById('addPriceInput'),
    addStorageInput: document.getElementById('addStorageInput'),
    addVendorSelect: document.getElementById('addVendorSelect'),
    addStatusSelect: document.getElementById('addStatusSelect'),
    addImageInput: document.getElementById('addImageInput'),
    btnSubmitAddModal: document.getElementById('btnSubmitAddModal'),
    addPreviewImage: document.getElementById('addPreviewImage'),
    previewBrandText: document.getElementById('previewBrandText'),
    previewModelText: document.getElementById('previewModelText'),
    previewStorageText: document.getElementById('previewStorageText'),
    previewVendorText: document.getElementById('previewVendorText'),
    previewPriceText: document.getElementById('previewPriceText'),
    previewStatusBadge: document.getElementById('previewStatusBadge'),

    // Edit Product Modal
    editMobileModalOverlay: document.getElementById('editMobileModalOverlay'),
    btnCloseEditModal: document.getElementById('btnCloseEditModal'),
    btnCancelEditModal: document.getElementById('btnCancelEditModal'),
    editMobileForm: document.getElementById('editMobileForm'),
    editModalAlert: document.getElementById('editModalAlert'),
    editMobileId: document.getElementById('editMobileId'),
    editDisplayId: document.getElementById('editDisplayId'),
    editDisplayTitle: document.getElementById('editDisplayTitle'),
    editDisplayCurrentPrice: document.getElementById('editDisplayCurrentPrice'),
    editBrandInput: document.getElementById('editBrandInput'),
    editModelInput: document.getElementById('editModelInput'),
    editPriceInput: document.getElementById('editPriceInput'),
    editStorageInput: document.getElementById('editStorageInput'),
    editVendorSelect: document.getElementById('editVendorSelect'),
    editStatusSelect: document.getElementById('editStatusSelect'),
    editImageInput: document.getElementById('editImageInput'),
    editPriceDiffInfo: document.getElementById('editPriceDiffInfo'),
    btnSubmitEditModal: document.getElementById('btnSubmitEditModal'),
    editPreviewImage: document.getElementById('editPreviewImage'),
    editPreviewBrand: document.getElementById('editPreviewBrand'),
    editPreviewModel: document.getElementById('editPreviewModel'),
    editPreviewStorage: document.getElementById('editPreviewStorage'),
    editPreviewVendor: document.getElementById('editPreviewVendor'),
    editPreviewPrice: document.getElementById('editPreviewPrice'),
    editPreviewStatusBadge: document.getElementById('editPreviewStatusBadge'),

    // View Product Modal
    viewMobileModalOverlay: document.getElementById('viewMobileModalOverlay'),
    btnCloseViewModal: document.getElementById('btnCloseViewModal'),
    viewProductImage: document.getElementById('viewProductImage'),
    viewProductId: document.getElementById('viewProductId'),
    viewProductStatus: document.getElementById('viewProductStatus'),
    viewProductName: document.getElementById('viewProductName'),
    viewProductPrice: document.getElementById('viewProductPrice'),
    viewProductBrand: document.getElementById('viewProductBrand'),
    viewProductStorage: document.getElementById('viewProductStorage'),
    viewProductVendor: document.getElementById('viewProductVendor'),
    viewProductUpdated: document.getElementById('viewProductUpdated'),
    btnViewEditAction: document.getElementById('btnViewEditAction'),
    btnViewDeleteAction: document.getElementById('btnViewDeleteAction'),

    // Delete Modal
    deleteModalOverlay: document.getElementById('deleteModalOverlay'),
    btnCloseDeleteModal: document.getElementById('btnCloseDeleteModal'),
    btnCancelDeleteModal: document.getElementById('btnCancelDeleteModal'),
    deleteTargetImage: document.getElementById('deleteTargetImage'),
    deleteTargetId: document.getElementById('deleteTargetId'),
    deleteTargetName: document.getElementById('deleteTargetName'),
    deleteTargetPrice: document.getElementById('deleteTargetPrice'),
    btnConfirmDelete: document.getElementById('btnConfirmDelete'),

    // Add Vendor Modal
    addVendorModalOverlay: document.getElementById('addVendorModalOverlay'),
    btnCloseAddVendorModal: document.getElementById('btnCloseAddVendorModal'),
    btnCancelAddVendorModal: document.getElementById('btnCancelAddVendorModal'),
    addVendorForm: document.getElementById('addVendorForm'),
    addVendorModalAlert: document.getElementById('addVendorModalAlert'),
    addVendorNameInput: document.getElementById('addVendorNameInput'),
    addVendorCodeInput: document.getElementById('addVendorCodeInput'),
    addVendorCategoryInput: document.getElementById('addVendorCategoryInput'),
    addVendorEmailInput: document.getElementById('addVendorEmailInput'),
    addVendorPhoneInput: document.getElementById('addVendorPhoneInput'),
    addVendorLocationInput: document.getElementById('addVendorLocationInput'),
    btnSubmitAddVendorModal: document.getElementById('btnSubmitAddVendorModal'),

    // Toast Container
    toastContainer: document.getElementById('toastContainer')
  };

  // =========================================================================
  // 4. UI FEEDBACK: TOASTS & ALERTS
  // =========================================================================
  function showToast(title, message, type = 'info') {
    if (!dom.toastContainer) return;
    const toast = document.createElement('div');
    toast.className = `toast-item ${type}`;

    let iconClass = 'bi-info-circle-fill';
    if (type === 'success') iconClass = 'bi-check-circle-fill';
    if (type === 'error') iconClass = 'bi-exclamation-octagon-fill';
    if (type === 'warning') iconClass = 'bi-exclamation-triangle-fill';

    toast.innerHTML = `
      <i class="bi ${iconClass} toast-icon"></i>
      <div class="toast-content">
        <div class="toast-title">${escapeHTML(title)}</div>
        <div class="toast-msg">${escapeHTML(message)}</div>
      </div>
      <button class="toast-close" aria-label="Close notification">&times;</button>
    `;

    const closeBtn = toast.querySelector('.toast-close');
    closeBtn.addEventListener('click', () => removeToast(toast));

    dom.toastContainer.appendChild(toast);

    setTimeout(() => {
      removeToast(toast);
    }, 4500);
  }

  function removeToast(toast) {
    toast.classList.add('toast-fade-out');
    setTimeout(() => {
      if (toast.parentNode) toast.parentNode.removeChild(toast);
    }, 250);
  }

  function showModalAlert(alertEl, msg, type = 'error') {
    if (!alertEl) return;
    alertEl.className = `modal-alert alert-${type}`;
    const icon = type === 'success' ? 'bi-check-circle-fill' : 'bi-exclamation-triangle-fill';
    alertEl.innerHTML = `<i class="bi ${icon}"></i> <span>${escapeHTML(msg)}</span>`;
    alertEl.classList.remove('d-none');
  }

  function hideModalAlert(alertEl) {
    if (!alertEl) return;
    alertEl.classList.add('d-none');
    alertEl.innerHTML = '';
  }

  function escapeHTML(str) {
    if (!str) return '';
    return String(str)
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;')
      .replace(/'/g, '&#039;');
  }

  // Update backend status banner and badge
  function updateBackendStatus(online) {
    state.isBackendLive = online;
    if (dom.dataModeBadge && dom.dataModeLabel) {
      if (online) {
        dom.dataModeBadge.classList.add('online');
        dom.dataModeBadge.classList.remove('offline');
        dom.dataModeLabel.textContent = 'Redis Live (Port 5000)';
        dom.dataModeBadge.title = 'Connected live to Flask backend and Redis';
        if (dom.backendAlertBanner) dom.backendAlertBanner.classList.add('d-none');
        if (dom.settingsRedisStatus) {
          dom.settingsRedisStatus.textContent = 'Connected (Healthy)';
          dom.settingsRedisStatus.className = 'text-success';
        }
      } else {
        dom.dataModeBadge.classList.remove('online');
        dom.dataModeBadge.classList.add('offline');
        dom.dataModeLabel.textContent = 'Backend Offline';
        dom.dataModeBadge.title = 'Cannot reach Flask backend on http://localhost:5000';
        if (dom.backendAlertBanner) dom.backendAlertBanner.classList.remove('d-none');
        if (dom.settingsRedisStatus) {
          dom.settingsRedisStatus.textContent = 'Disconnected (Offline)';
          dom.settingsRedisStatus.className = 'text-danger';
        }
      }
    }
  }

  // =========================================================================
  // 5. DATA LOADING & STATE SYNCHRONIZATION
  // =========================================================================
  async function loadData() {
    try {
      if (dom.refreshIcon) dom.refreshIcon.classList.add('spin');

      // 1. Check health
      const isHealthy = await ApiService.checkHealth();
      updateBackendStatus(isHealthy);

      if (!isHealthy) {
        showToast('Backend Disconnected', 'Cannot connect to Flask server at http://localhost:5000. Real-time updates paused.', 'error');
        renderEmptyState('Backend Connection Unavailable', 'Start Flask with python app.py or docker-compose up to connect to Redis.');
        return;
      }

      // 2. Fetch all products, vendors, and stats in parallel
      const [productsData, vendorsData, statsData] = await Promise.all([
        ApiService.getProducts(),
        ApiService.getVendors(),
        ApiService.getStats()
      ]);

      state.products = productsData || [];
      state.vendors = vendorsData || [];
      state.stats = statsData || null;

      // Update sidebar counts
      if (dom.navProductCount) dom.navProductCount.textContent = state.products.length;
      if (dom.navVendorCount) dom.navVendorCount.textContent = state.vendors.length;

      // Update summary cards
      renderVendorSummaryCards();

      // Update vendor pills & selects
      renderVendorPills();
      populateVendorSelects();

      // Update brand filter dropdown & pills
      populateBrandFilters();

      // Apply current search/filters and render table
      applyFiltersAndSort();

      // Render secondary views (overview, categories, analytics)
      renderOverviewView();
      renderCategoriesView();
      renderInventoryView();
      renderAnalyticsView();
      renderOrdersView();

    } catch (err) {
      console.error('Error loading data from backend:', err);
      updateBackendStatus(false);
      showToast('Data Load Error', err.message, 'error');
      renderEmptyState('Error Fetching Data', err.message);
    } finally {
      if (dom.refreshIcon) {
        setTimeout(() => dom.refreshIcon.classList.remove('spin'), 400);
      }
    }
  }

  // =========================================================================
  // 6. VENDOR MANAGEMENT & SUMMARY RENDERING (Requirement 3)
  // =========================================================================
  function renderVendorSummaryCards() {
    const products = state.products;
    const vendors = state.vendors;
    const stats = state.stats || {};

    const totalVendors = vendors.length;
    const totalProducts = products.length;
    const inStock = products.filter(m => m.status === 'In Stock' || m.status === 'Flagship').length;
    const outOfStock = products.filter(m => m.status === 'Out of Stock').length;
    const totalValue = products.reduce((acc, m) => acc + (Number(m.price) || 0), 0);

    if (dom.statVendorTotal) dom.statVendorTotal.textContent = totalVendors;
    if (dom.statTotalProducts) dom.statTotalProducts.textContent = totalProducts;
    if (dom.statInStockCount) dom.statInStockCount.textContent = inStock;
    if (dom.statOutOfStockCount) dom.statOutOfStockCount.textContent = outOfStock;
    if (dom.statTotalValue) dom.statTotalValue.textContent = formatINR(totalValue);

    if (dom.statInStockPct && totalProducts > 0) {
      const pct = Math.round((inStock / totalProducts) * 100);
      dom.statInStockPct.textContent = `${pct}% available now`;
    }
  }

  function renderVendorPills() {
    if (!dom.vendorPillsBar) return;
    dom.vendorPillsBar.innerHTML = '';

    // "All Vendors" pill
    const allPill = document.createElement('button');
    allPill.type = 'button';
    allPill.className = `vendor-pill ${state.activeVendorFilter === null ? 'active' : ''}`;
    allPill.innerHTML = `<span>All Vendors</span> <span class="vendor-pill-count">${state.products.length}</span>`;
    allPill.addEventListener('click', () => {
      state.activeVendorFilter = null;
      renderVendorPills();
      updateSelectedVendorStrip();
      applyFiltersAndSort();
    });
    dom.vendorPillsBar.appendChild(allPill);

    // Each vendor pill
    state.vendors.forEach(v => {
      const vProducts = state.products.filter(m => m.vendor_id === v.id);
      const pill = document.createElement('button');
      pill.type = 'button';
      pill.className = `vendor-pill ${state.activeVendorFilter === v.id ? 'active' : ''}`;
      pill.innerHTML = `<span>${escapeHTML(v.name)}</span> <span class="vendor-pill-count">${vProducts.length}</span>`;
      pill.addEventListener('click', () => {
        state.activeVendorFilter = v.id;
        renderVendorPills();
        updateSelectedVendorStrip();
        applyFiltersAndSort();
      });
      dom.vendorPillsBar.appendChild(pill);
    });

    updateSelectedVendorStrip();
  }

  function updateSelectedVendorStrip() {
    if (!dom.selectedVendorStrip) return;
    if (state.activeVendorFilter === null) {
      dom.selectedVendorStrip.classList.add('d-none');
      return;
    }

    const vendor = state.vendors.find(v => v.id === state.activeVendorFilter);
    if (!vendor) {
      dom.selectedVendorStrip.classList.add('d-none');
      return;
    }

    const vProducts = state.products.filter(m => m.vendor_id === vendor.id);

    dom.stripVendorName.textContent = vendor.name;
    dom.stripVendorCode.textContent = vendor.code || `VEN-${vendor.id}`;
    dom.stripVendorEmail.textContent = vendor.email || 'partner@coherentmobiles.com';
    dom.stripVendorPhone.textContent = vendor.phone || '+91 98765 43210';
    dom.stripVendorLocation.textContent = vendor.location || 'India';
    dom.stripVendorRating.textContent = `${vendor.rating || 4.8} / 5.0`;
    dom.stripVendorProductCount.textContent = vProducts.length;

    dom.selectedVendorStrip.classList.remove('d-none');
  }

  function populateVendorSelects() {
    const selects = [dom.addVendorSelect, dom.editVendorSelect];
    selects.forEach(sel => {
      if (!sel) return;
      sel.innerHTML = '';
      state.vendors.forEach(v => {
        const opt = document.createElement('option');
        opt.value = v.id;
        opt.textContent = `${v.name} (${v.code || 'VEN-' + v.id})`;
        sel.appendChild(opt);
      });
    });
  }

  function populateBrandFilters() {
    const brands = [...new Set(state.products.map(m => m.brand).filter(Boolean))].sort();

    // 1. Select dropdown
    if (dom.brandSelectFilter) {
      const currentVal = dom.brandSelectFilter.value;
      dom.brandSelectFilter.innerHTML = '<option value="">All Brands</option>';
      brands.forEach(b => {
        const opt = document.createElement('option');
        opt.value = b;
        opt.textContent = b;
        if (b === currentVal) opt.selected = true;
        dom.brandSelectFilter.appendChild(opt);
      });
    }

    // 2. Brand pills quick filter
    if (dom.brandPillsBar) {
      dom.brandPillsBar.innerHTML = '';
      const allChip = document.createElement('button');
      allChip.type = 'button';
      allChip.className = `brand-chip ${!state.brandFilter ? 'active' : ''}`;
      allChip.textContent = 'All';
      allChip.addEventListener('click', () => {
        state.brandFilter = '';
        if (dom.brandSelectFilter) dom.brandSelectFilter.value = '';
        applyFiltersAndSort();
      });
      dom.brandPillsBar.appendChild(allChip);

      brands.forEach(b => {
        const chip = document.createElement('button');
        chip.type = 'button';
        chip.className = `brand-chip ${state.brandFilter.toLowerCase() === b.toLowerCase() ? 'active' : ''}`;
        chip.textContent = b;
        chip.addEventListener('click', () => {
          state.brandFilter = b;
          if (dom.brandSelectFilter) dom.brandSelectFilter.value = b;
          applyFiltersAndSort();
        });
        dom.brandPillsBar.appendChild(chip);
      });
    }
  }

  // =========================================================================
  // 7. FILTER, SEARCH, SORT & PAGINATION LOGIC
  // =========================================================================
  function applyFiltersAndSort() {
    let list = [...state.products];

    // Filter by Active Vendor (if vendor tab selected)
    if (state.activeVendorFilter !== null) {
      list = list.filter(m => m.vendor_id === state.activeVendorFilter);
    }

    // Filter by Brand
    if (state.brandFilter) {
      const bLow = state.brandFilter.toLowerCase();
      list = list.filter(m => (m.brand || '').toLowerCase() === bLow);
    }

    // Filter by Stock Status
    if (state.statusFilter) {
      const sLow = state.statusFilter.toLowerCase();
      list = list.filter(m => (m.status || '').toLowerCase() === sLow);
    }

    // Search Query (brand, model, id, vendor_name)
    if (state.searchQuery) {
      const q = state.searchQuery.toLowerCase().trim();
      list = list.filter(m =>
        (m.brand || '').toLowerCase().includes(q) ||
        (m.model || '').toLowerCase().includes(q) ||
        String(m.id).includes(q) ||
        (m.vendor_name || '').toLowerCase().includes(q) ||
        (m.storage || '').toLowerCase().includes(q)
      );
    }

    // Sort By
    switch (state.sortBy) {
      case 'price-asc':
        list.sort((a, b) => Number(a.price) - Number(b.price));
        break;
      case 'price-desc':
        list.sort((a, b) => Number(b.price) - Number(a.price));
        break;
      case 'name-asc':
        list.sort((a, b) => (a.model || '').localeCompare(b.model || ''));
        break;
      case 'name-desc':
        list.sort((a, b) => (b.model || '').localeCompare(a.model || ''));
        break;
      case 'id-desc':
        list.sort((a, b) => Number(b.id) - Number(a.id));
        break;
      case 'id-asc':
      default:
        list.sort((a, b) => Number(a.id) - Number(b.id));
        break;
    }

    state.filteredProducts = list;

    // Reset pagination to page 1 if current page exceeds total pages
    const totalItems = list.length;
    const pageSize = state.pagination.pageSize;
    const totalPages = Math.max(1, Math.ceil(totalItems / pageSize));
    state.pagination.totalPages = totalPages;
    if (state.pagination.currentPage > totalPages) {
      state.pagination.currentPage = 1;
    }

    // Update Counter Badges
    if (dom.recordsBadge) {
      dom.recordsBadge.textContent = `${totalItems} product${totalItems === 1 ? '' : 's'}`;
    }
    if (dom.totalCountText) dom.totalCountText.textContent = state.products.length;
    if (dom.showingCountText) dom.showingCountText.textContent = totalItems;

    // Render Table or Grid
    renderProductsDisplay();
    renderPagination();
  }

  // =========================================================================
  // 8. RENDER PRODUCTS TABLE & SHOWCASE GRID
  // =========================================================================
  function renderProductsDisplay() {
    const list = state.filteredProducts;

    if (list.length === 0) {
      if (dom.tableContainer) dom.tableContainer.classList.add('d-none');
      if (dom.cardsGridView) dom.cardsGridView.classList.add('d-none');
      if (dom.emptyState) dom.emptyState.classList.remove('d-none');
      return;
    }

    if (dom.emptyState) dom.emptyState.classList.add('d-none');

    // Slice for current page
    const start = (state.pagination.currentPage - 1) * state.pagination.pageSize;
    const end = start + state.pagination.pageSize;
    const pageItems = list.slice(start, end);

    if (state.viewMode === 'table') {
      if (dom.tableContainer) dom.tableContainer.classList.remove('d-none');
      if (dom.cardsGridView) dom.cardsGridView.classList.add('d-none');
      renderTableRows(pageItems);
    } else {
      if (dom.tableContainer) dom.tableContainer.classList.add('d-none');
      if (dom.cardsGridView) dom.cardsGridView.classList.remove('d-none');
      renderCardsGrid(pageItems);
    }
  }

  function renderTableRows(items) {
    if (!dom.inventoryTableBody) return;
    dom.inventoryTableBody.innerHTML = '';

    items.forEach(p => {
      const tr = document.createElement('tr');
      tr.dataset.id = p.id;

      const imgSrc = p.image || resolveImage(p.brand, p.model);
      const statusClass = getStatusClass(p.status, p.price);
      const formattedDate = formatDate(p.updated_at);
      const vendorName = p.vendor_name || getVendorName(p.vendor_id);

      tr.innerHTML = `
        <td>
          <img class="product-thumb" src="${escapeHTML(imgSrc)}" alt="${escapeHTML(p.model)}" onerror="this.src='images/iphone15.jpg'">
        </td>
        <td>
          <span class="device-id-badge">#${p.id}</span>
        </td>
        <td>
          <span class="product-brand-tag">${escapeHTML(p.brand)}</span>
        </td>
        <td class="product-name-cell">
          <strong>${escapeHTML(p.model)}</strong>
          <small>${escapeHTML(p.brand)} &bull; ${escapeHTML(p.storage || '128 GB')}</small>
        </td>
        <td>
          <strong>${escapeHTML(p.storage || '128 GB')}</strong>
        </td>
        <td>
          <span class="product-price">${formatINR(p.price)}</span>
        </td>
        <td>
          <span class="status-badge ${statusClass}">${escapeHTML(p.status || 'In Stock')}</span>
        </td>
        <td>
          <span class="vendor-tag-link" title="Vendor: ${escapeHTML(vendorName)}">
            <i class="bi bi-shop"></i>
            <span>${escapeHTML(vendorName)}</span>
          </span>
        </td>
        <td>
          <span class="date-text">${formattedDate}</span>
        </td>
        <td class="text-right">
          <div class="table-actions">
            <button class="action-btn btn-view-act" data-action="view" data-id="${p.id}" title="View details">
              <i class="bi bi-eye"></i>
            </button>
            <button class="action-btn btn-edit-act" data-action="edit" data-id="${p.id}" title="Edit product">
              <i class="bi bi-pencil"></i>
            </button>
            <button class="action-btn btn-delete-act" data-action="delete" data-id="${p.id}" title="Delete product">
              <i class="bi bi-trash3"></i>
            </button>
          </div>
        </td>
      `;

      dom.inventoryTableBody.appendChild(tr);
    });

    // Attach row action listeners
    attachActionListeners(dom.inventoryTableBody);
  }

  function renderCardsGrid(items) {
    if (!dom.cardsGridView) return;
    dom.cardsGridView.innerHTML = '';

    items.forEach(p => {
      const card = document.createElement('div');
      card.className = 'product-card-grid';
      card.dataset.id = p.id;

      const imgSrc = p.image || resolveImage(p.brand, p.model);
      const statusClass = getStatusClass(p.status, p.price);
      const vendorName = p.vendor_name || getVendorName(p.vendor_id);

      card.innerHTML = `
        <div class="card-grid-thumb">
          <span class="device-id-badge card-grid-id">#${p.id}</span>
          <span class="status-badge ${statusClass} card-grid-status">${escapeHTML(p.status || 'In Stock')}</span>
          <img src="${escapeHTML(imgSrc)}" alt="${escapeHTML(p.model)}" onerror="this.src='images/iphone15.jpg'">
        </div>
        <div class="card-grid-body">
          <span class="card-grid-brand">${escapeHTML(p.brand)}</span>
          <h4 class="card-grid-name">${escapeHTML(p.model)}</h4>
          <div class="card-grid-meta">
            <span><i class="bi bi-hdd"></i> ${escapeHTML(p.storage || '128 GB')}</span>
            <span><i class="bi bi-shop"></i> ${escapeHTML(vendorName)}</span>
          </div>
          <div class="card-grid-footer">
            <span class="card-grid-price">${formatINR(p.price)}</span>
            <div class="table-actions">
              <button class="action-btn btn-view-act" data-action="view" data-id="${p.id}" title="View details">
                <i class="bi bi-eye"></i>
              </button>
              <button class="action-btn btn-edit-act" data-action="edit" data-id="${p.id}" title="Edit product">
                <i class="bi bi-pencil"></i>
              </button>
              <button class="action-btn btn-delete-act" data-action="delete" data-id="${p.id}" title="Delete product">
                <i class="bi bi-trash3"></i>
              </button>
            </div>
          </div>
        </div>
      `;

      dom.cardsGridView.appendChild(card);
    });

    attachActionListeners(dom.cardsGridView);
  }

  function attachActionListeners(container) {
    const buttons = container.querySelectorAll('.action-btn[data-action]');
    buttons.forEach(btn => {
      btn.addEventListener('click', (e) => {
        e.stopPropagation();
        const action = btn.dataset.action;
        const id = Number(btn.dataset.id);
        if (action === 'view') openViewModal(id);
        if (action === 'edit') openEditModal(id);
        if (action === 'delete') openDeleteModal(id);
      });
    });
  }

  function getStatusClass(status, price) {
    const s = String(status || '').toLowerCase();
    if (s.includes('out of stock')) return 'out-of-stock';
    if (s.includes('low stock')) return 'low-stock';
    if (s.includes('flagship') || Number(price) > 80000) return 'flagship';
    return 'in-stock';
  }

  function getVendorName(vendorId) {
    const v = state.vendors.find(item => item.id === Number(vendorId));
    return v ? v.name : 'Coherent Retail Direct';
  }

  function renderEmptyState(title, message) {
    if (dom.tableContainer) dom.tableContainer.classList.add('d-none');
    if (dom.cardsGridView) dom.cardsGridView.classList.add('d-none');
    if (dom.emptyState) {
      dom.emptyState.classList.remove('d-none');
      const h4 = dom.emptyState.querySelector('h4');
      const p = dom.emptyState.querySelector('p');
      if (h4) h4.textContent = title;
      if (p) p.textContent = message;
    }
  }

  function renderPagination() {
    if (!dom.paginationControls) return;
    const { currentPage, totalPages } = state.pagination;
    if (dom.pageIndicator) {
      dom.pageIndicator.textContent = `Page ${currentPage} of ${totalPages}`;
    }
    if (dom.btnPrevPage) dom.btnPrevPage.disabled = currentPage <= 1;
    if (dom.btnNextPage) dom.btnNextPage.disabled = currentPage >= totalPages;
  }

  // =========================================================================
  // 9. OVERVIEW, CATEGORIES, INVENTORY & ANALYTICS VIEWS (Dynamic Backend Data)
  // =========================================================================
  function renderOverviewView() {
    const products = state.products;
    const stats = state.stats || {};

    const totalCount = products.length;
    const totalVal = products.reduce((acc, m) => acc + (Number(m.price) || 0), 0);
    const avgPrice = totalCount > 0 ? totalVal / totalCount : 0;
    const flagshipCount = products.filter(m => Number(m.price) > 80000 || m.status === 'Flagship').length;
    const inStockCount = products.filter(m => m.status === 'In Stock' || m.status === 'Flagship').length;
    const stockHealthPct = totalCount > 0 ? Math.round((inStockCount / totalCount) * 100) : 100;

    if (dom.ovAvgPrice) dom.ovAvgPrice.textContent = formatINR(avgPrice);
    if (dom.ovFlagshipCount) dom.ovFlagshipCount.textContent = flagshipCount;
    if (dom.ovStockHealth) dom.ovStockHealth.textContent = `${stockHealthPct}%`;
    if (dom.ovVendorCount) dom.ovVendorCount.textContent = state.vendors.length;

    // Brand Market Share Bars
    renderBrandStatsGrid();

    // Top 5 Expensive Smartphones
    renderTopExpensiveList();

    // Activity Feed
    renderActivityFeed();
  }

  function renderBrandStatsGrid() {
    if (!dom.brandStatsGrid) return;
    dom.brandStatsGrid.innerHTML = '';

    const products = state.products;
    const brands = [...new Set(products.map(m => m.brand).filter(Boolean))].sort();
    const totalCount = products.length;

    if (totalCount === 0) {
      dom.brandStatsGrid.innerHTML = '<p class="text-muted">No inventory data available.</p>';
      return;
    }

    brands.forEach(brand => {
      const bItems = products.filter(m => (m.brand || '').toLowerCase() === brand.toLowerCase());
      const bCount = bItems.length;
      const bVal = bItems.reduce((acc, m) => acc + (Number(m.price) || 0), 0);
      const bPct = Math.round((bCount / totalCount) * 100);

      const row = document.createElement('div');
      row.className = 'brand-bar-row';
      row.innerHTML = `
        <div class="brand-bar-header">
          <strong>${escapeHTML(brand)} (${bCount} models)</strong>
          <span>${formatINR(bVal)} &bull; ${bPct}%</span>
        </div>
        <div class="brand-bar-track">
          <div class="brand-bar-fill" style="width: ${bPct}%;"></div>
        </div>
      `;
      dom.brandStatsGrid.appendChild(row);
    });
  }

  function renderTopExpensiveList() {
    if (!dom.topExpensiveList) return;
    dom.topExpensiveList.innerHTML = '';

    const sorted = [...state.products].sort((a, b) => Number(b.price) - Number(a.price)).slice(0, 5);
    if (sorted.length === 0) {
      dom.topExpensiveList.innerHTML = '<p class="text-muted">No products available.</p>';
      return;
    }

    sorted.forEach((p, idx) => {
      const item = document.createElement('div');
      item.className = 'expensive-item';
      const imgSrc = p.image || resolveImage(p.brand, p.model);
      item.innerHTML = `
        <span class="device-id-badge">#${idx + 1}</span>
        <img class="expensive-thumb" src="${escapeHTML(imgSrc)}" alt="${escapeHTML(p.model)}" onerror="this.src='images/iphone15.jpg'">
        <div class="expensive-info">
          <strong>${escapeHTML(p.brand)} ${escapeHTML(p.model)}</strong>
          <small>${escapeHTML(p.storage || '128 GB')} &bull; ${escapeHTML(p.vendor_name || 'Vendor')}</small>
        </div>
        <span class="expensive-price">${formatINR(p.price)}</span>
      `;
      dom.topExpensiveList.appendChild(item);
    });
  }

  function renderActivityFeed() {
    if (!dom.activityFeed) return;
    dom.activityFeed.innerHTML = '';

    const logs = (state.stats && state.stats.recent_activity) || [];
    if (logs.length === 0) {
      dom.activityFeed.innerHTML = `
        <div class="activity-item">
          <i class="bi bi-clock-history text-muted"></i>
          <div>
            <p><strong>System Initialized</strong></p>
            <small class="text-muted">Redis persistence session active on Port 5000.</small>
          </div>
        </div>
      `;
      return;
    }

    logs.forEach(log => {
      const item = document.createElement('div');
      item.className = 'activity-item';
      let icon = 'bi-info-circle text-primary';
      if (log.action === 'CREATED') icon = 'bi-plus-circle-fill text-success';
      if (log.action === 'UPDATED') icon = 'bi-pencil-fill text-warning';
      if (log.action === 'DELETED') icon = 'bi-trash-fill text-danger';

      item.innerHTML = `
        <i class="bi ${icon}"></i>
        <div>
          <p>${escapeHTML(log.description || log.action)}</p>
          <small class="text-muted">${formatDate(log.timestamp)}</small>
        </div>
      `;
      dom.activityFeed.appendChild(item);
    });
  }

  function renderCategoriesView() {
    if (!dom.categoriesGrid) return;
    dom.categoriesGrid.innerHTML = '';

    const products = state.products;
    const brands = [...new Set(products.map(m => m.brand).filter(Boolean))].sort();

    brands.forEach(brand => {
      const bItems = products.filter(m => (m.brand || '').toLowerCase() === brand.toLowerCase());
      const card = document.createElement('div');
      card.className = 'section-card';
      card.style.marginBottom = '16px';
      card.innerHTML = `
        <div class="card-header-simple">
          <div>
            <span class="eyebrow">BRAND SERIES</span>
            <h3>${escapeHTML(brand)}</h3>
          </div>
          <span class="badge-tag">${bItems.length} Products</span>
        </div>
        <p class="text-muted" style="margin-bottom: 12px;">Models registered under ${escapeHTML(brand)} in inventory:</p>
        <ul style="padding-left: 20px;">
          ${bItems.map(m => `<li><strong>${escapeHTML(m.model)}</strong> — ${escapeHTML(m.storage)} (${formatINR(m.price)}) &bull; <span class="status-badge ${getStatusClass(m.status, m.price)}">${escapeHTML(m.status)}</span></li>`).join('')}
        </ul>
      `;
      dom.categoriesGrid.appendChild(card);
    });
  }

  function renderInventoryView() {
    if (!dom.inventoryStatusSummary) return;
    const inStock = state.products.filter(m => m.status === 'In Stock' || m.status === 'Flagship');
    const lowStock = state.products.filter(m => m.status === 'Low Stock');
    const outOfStock = state.products.filter(m => m.status === 'Out of Stock');

    dom.inventoryStatusSummary.innerHTML = `
      <div class="overview-stats-grid" style="margin-bottom: 20px;">
        <div class="overview-stat-tile">
          <span class="tile-label">Fully Stocked</span>
          <h4 class="tile-val text-success">${inStock.length} Products</h4>
          <small class="tile-hint">Available for instant dispatch</small>
        </div>
        <div class="overview-stat-tile">
          <span class="tile-label">Low Stock Warning</span>
          <h4 class="tile-val text-warning">${lowStock.length} Products</h4>
          <small class="tile-hint">Approaching minimum threshold</small>
        </div>
        <div class="overview-stat-tile">
          <span class="tile-label">Out of Stock</span>
          <h4 class="tile-val text-danger">${outOfStock.length} Products</h4>
          <small class="tile-hint">Requires vendor restock</small>
        </div>
        <div class="overview-stat-tile">
          <span class="tile-label">Warehouse Locations</span>
          <h4 class="tile-val text-primary">4 Regional Hubs</h4>
          <small class="tile-hint">Mumbai, Bengaluru, Delhi, Hyderabad</small>
        </div>
      </div>
    `;
  }

  function renderAnalyticsView() {
    if (!dom.analyticsDetailContainer) return;
    const totalVal = state.products.reduce((acc, m) => acc + (Number(m.price) || 0), 0);
    const avgPrice = state.products.length > 0 ? totalVal / state.products.length : 0;

    dom.analyticsDetailContainer.innerHTML = `
      <div class="overview-stats-grid">
        <div class="overview-stat-tile">
          <span class="tile-label">Portfolio Gross Value</span>
          <h4 class="tile-val text-primary">${formatINR(totalVal)}</h4>
          <small class="tile-hint">Total asset valuation across all vendors</small>
        </div>
        <div class="overview-stat-tile">
          <span class="tile-label">Average Unit Valuation</span>
          <h4 class="tile-val">${formatINR(avgPrice)}</h4>
          <small class="tile-hint">Median smartphone selling price</small>
        </div>
      </div>
      <div style="margin-top: 24px;">
        <h4 style="font-size: 15px; font-weight: 800; margin-bottom: 12px;">Vendor Asset Allocations</h4>
        <div class="table-container">
          <table class="crud-table">
            <thead>
              <tr>
                <th>Vendor Name</th>
                <th>Code</th>
                <th>Products</th>
                <th>In Stock</th>
                <th>Valuation</th>
                <th>Rating</th>
              </tr>
            </thead>
            <tbody>
              ${state.vendors.map(v => `
                <tr>
                  <td><strong>${escapeHTML(v.name)}</strong></td>
                  <td><code>${escapeHTML(v.code)}</code></td>
                  <td>${v.product_count || 0}</td>
                  <td><span class="text-success">${v.in_stock_count || 0}</span></td>
                  <td><strong>${formatINR(v.inventory_value || 0)}</strong></td>
                  <td><i class="bi bi-star-fill text-warning"></i> ${v.rating || 4.8}</td>
                </tr>
              `).join('')}
            </tbody>
          </table>
        </div>
      </div>
    `;
  }

  // --- ORDERS VIEW RENDERING ---
  async function renderOrdersView() {
    const tbody = document.getElementById('ordersTableBody');
    if (!tbody) return;
    try {
      const res = await fetch(`${API_BASE_URL}/orders`);
      if (!res.ok) return;
      const data = await res.json();
      const orders = data.orders || [];

      const badge = document.getElementById('navOrders');
      if (badge) {
        const countBadge = badge.querySelector('.nav-count-badge');
        if (countBadge) countBadge.textContent = orders.length;
      }

      if (orders.length === 0) {
        tbody.innerHTML = `<tr><td colspan="7" class="text-center p-4 text-muted">No customer orders recorded yet. Orders placed on the storefront will appear here automatically.</td></tr>`;
        return;
      }

      tbody.innerHTML = orders.map(o => {
        const statusClass = (o.status === 'Confirmed' || o.status === 'Completed')
          ? 'in-stock'
          : (o.status === 'Dispatched' ? 'flagship' : 'low-stock');
        return `
          <tr>
            <td><code>#${escapeHTML(o.id)}</code></td>
            <td>
              <strong>${escapeHTML(o.customer_name)}</strong>
              ${o.customer_phone ? `<div style="font-size:11.5px;color:var(--text-muted)">📞 ${escapeHTML(o.customer_phone)}</div>` : ''}
            </td>
            <td>
              ${escapeHTML(o.device_name)}
              <span class="text-muted" style="font-size:12px">(${escapeHTML(o.storage || '128 GB')})</span>
            </td>
            <td>
              <span class="badge-tag">${escapeHTML(o.fulfillment_type || 'Doorstep Delivery')}</span>
            </td>
            <td>
              <strong>${formatINR(o.amount)}</strong>
            </td>
            <td>
              <span class="status-badge ${statusClass}">${escapeHTML(o.status || 'Confirmed')}</span>
            </td>
            <td style="text-align:right">
              <select class="status-select-sm" data-order-id="${escapeHTML(o.id)}" style="padding:4px 8px;font-size:12px;border-radius:6px;border:1px solid var(--border);background:#fff;cursor:pointer">
                <option value="Confirmed" ${o.status === 'Confirmed' ? 'selected' : ''}>Confirmed</option>
                <option value="Dispatched" ${o.status === 'Dispatched' ? 'selected' : ''}>Dispatched</option>
                <option value="Inspected" ${o.status === 'Inspected' ? 'selected' : ''}>Inspected</option>
                <option value="Completed" ${o.status === 'Completed' ? 'selected' : ''}>Completed</option>
                <option value="Cancelled" ${o.status === 'Cancelled' ? 'selected' : ''}>Cancelled</option>
              </select>
            </td>
          </tr>
        `;
      }).join('');

      tbody.querySelectorAll('.status-select-sm').forEach(sel => {
        sel.addEventListener('change', async (e) => {
          const ordId = e.target.getAttribute('data-order-id');
          const newStatus = e.target.value;
          try {
            const updateRes = await fetch(`${API_BASE_URL}/orders/${ordId}`, {
              method: 'PUT',
              headers: { 'Content-Type': 'application/json' },
              body: JSON.stringify({ status: newStatus })
            });
            if (updateRes.ok) {
              showToast('Order Status Updated', `Order #${ordId} marked as ${newStatus}`, 'success');
              renderOrdersView();
            }
          } catch (err) {
            showToast('Update Failed', err.message, 'error');
          }
        });
      });
    } catch (e) {
      console.warn("Could not fetch orders:", e);
    }
  }

  // =========================================================================
  // 10. MODAL DIALOGS: ADD, EDIT, VIEW, DELETE & REGISTER VENDOR
  // =========================================================================

  // --- ADD PRODUCT MODAL ---
  function openAddModal() {
    hideModalAlert(dom.addModalAlert);
    dom.addMobileForm.reset();
    if (dom.addStorageInput) dom.addStorageInput.value = '128 GB';
    if (dom.addStatusSelect) dom.addStatusSelect.value = 'In Stock';
    updateAddPreview();
    dom.addMobileModalOverlay.classList.remove('d-none');
    setTimeout(() => dom.addBrandInput && dom.addBrandInput.focus(), 50);
  }

  function closeAddModal() {
    dom.addMobileModalOverlay.classList.add('d-none');
    hideModalAlert(dom.addModalAlert);
  }

  function updateAddPreview() {
    const brand = (dom.addBrandInput.value || 'Apple').trim();
    const model = (dom.addModelInput.value || 'iPhone 15').trim();
    const price = Number(dom.addPriceInput.value) || 69999;
    const storage = dom.addStorageInput.value || '128 GB';
    const vendorId = dom.addVendorSelect.value;
    const status = dom.addStatusSelect.value || 'In Stock';
    const customImg = dom.addImageInput.value.trim();

    dom.previewBrandText.textContent = brand;
    dom.previewModelText.textContent = model;
    dom.previewPriceText.textContent = formatINR(price);
    dom.previewStorageText.textContent = storage;
    dom.previewVendorText.textContent = getVendorName(vendorId);

    dom.previewStatusBadge.textContent = status;
    dom.previewStatusBadge.className = `status-badge ${getStatusClass(status, price)}`;

    const imgSrc = customImg || resolveImage(brand, model);
    dom.addPreviewImage.src = imgSrc;
  }

  async function handleAddSubmit(e) {
    e.preventDefault();
    hideModalAlert(dom.addModalAlert);

    const brand = dom.addBrandInput.value.trim();
    const model = dom.addModelInput.value.trim();
    const priceVal = dom.addPriceInput.value.trim();
    const storage = dom.addStorageInput.value.trim();
    const vendor_id = Number(dom.addVendorSelect.value) || 1;
    const status = dom.addStatusSelect.value;
    const image = dom.addImageInput.value.trim() || resolveImage(brand, model);

    // Form Validations (Requirement 4)
    if (!brand) {
      showModalAlert(dom.addModalAlert, 'Brand name is required.');
      dom.addBrandInput.focus();
      return;
    }

    if (!model) {
      showModalAlert(dom.addModalAlert, 'Product/Model name is required.');
      dom.addModelInput.focus();
      return;
    }

    if (!priceVal) {
      showModalAlert(dom.addModalAlert, 'Selling price is required.');
      dom.addPriceInput.focus();
      return;
    }

    const price = Number(priceVal);
    if (isNaN(price)) {
      showModalAlert(dom.addModalAlert, 'Selling price must be a valid number.');
      dom.addPriceInput.focus();
      return;
    }

    if (price < 0) {
      showModalAlert(dom.addModalAlert, 'Price cannot be negative.');
      dom.addPriceInput.focus();
      return;
    }

    // Duplicate submission prevention
    setButtonLoading(dom.btnSubmitAddModal, true);

    try {
      const created = await ApiService.createProduct({
        brand,
        model,
        price,
        storage,
        status,
        vendor_id,
        image
      });

      closeAddModal();
      showToast('Product Added', `"${created.brand} ${created.model}" has been saved to Redis inventory.`, 'success');
      await loadData();

    } catch (err) {
      showModalAlert(dom.addModalAlert, err.message);
      showToast('Error Adding Product', err.message, 'error');
    } finally {
      setButtonLoading(dom.btnSubmitAddModal, false);
    }
  }

  // --- EDIT PRODUCT MODAL ---
  async function openEditModal(id) {
    hideModalAlert(dom.editModalAlert);
    state.editingProductId = id;

    const product = state.products.find(m => m.id === Number(id));
    if (!product) {
      showToast('Error', `Product #${id} not found`, 'error');
      return;
    }

    dom.editMobileId.value = product.id;
    dom.editDisplayId.textContent = `ID #${product.id}`;
    dom.editDisplayTitle.textContent = `${product.brand} ${product.model}`;
    dom.editDisplayCurrentPrice.textContent = formatINR(product.price);

    dom.editBrandInput.value = product.brand || '';
    dom.editModelInput.value = product.model || '';
    dom.editPriceInput.value = product.price || '';
    dom.editStorageInput.value = product.storage || '128 GB';
    dom.editVendorSelect.value = product.vendor_id || 1;
    dom.editStatusSelect.value = product.status || 'In Stock';
    dom.editImageInput.value = product.image || '';

    updateEditPreview();
    dom.editMobileModalOverlay.classList.remove('d-none');
    setTimeout(() => dom.editPriceInput && dom.editPriceInput.focus(), 50);
  }

  function closeEditModal() {
    dom.editMobileModalOverlay.classList.add('d-none');
    hideModalAlert(dom.editModalAlert);
    state.editingProductId = null;
  }

  function updateEditPreview() {
    const brand = dom.editBrandInput.value.trim() || 'Brand';
    const model = dom.editModelInput.value.trim() || 'Model';
    const newPrice = Number(dom.editPriceInput.value) || 0;
    const storage = dom.editStorageInput.value;
    const vendorId = dom.editVendorSelect.value;
    const status = dom.editStatusSelect.value;
    const customImg = dom.editImageInput.value.trim();

    dom.editPreviewBrand.textContent = brand;
    dom.editPreviewModel.textContent = model;
    dom.editPreviewPrice.textContent = formatINR(newPrice);
    dom.editPreviewStorage.textContent = storage;
    dom.editPreviewVendor.textContent = getVendorName(vendorId);

    dom.editPreviewStatusBadge.textContent = status;
    dom.editPreviewStatusBadge.className = `status-badge ${getStatusClass(status, newPrice)}`;

    const imgSrc = customImg || resolveImage(brand, model);
    dom.editPreviewImage.src = imgSrc;

    // Price difference indicator
    const currentProduct = state.products.find(m => m.id === Number(dom.editMobileId.value));
    if (currentProduct && dom.editPriceDiffInfo) {
      const oldPrice = Number(currentProduct.price) || 0;
      const diff = newPrice - oldPrice;
      if (diff > 0) {
        dom.editPriceDiffInfo.innerHTML = `<span class="text-success"><i class="bi bi-arrow-up"></i> +${formatINR(diff)} price increase</span>`;
      } else if (diff < 0) {
        dom.editPriceDiffInfo.innerHTML = `<span class="text-danger"><i class="bi bi-arrow-down"></i> ${formatINR(diff)} discount</span>`;
      } else {
        dom.editPriceDiffInfo.textContent = 'Price unchanged';
      }
    }
  }

  async function handleEditSubmit(e) {
    e.preventDefault();
    hideModalAlert(dom.editModalAlert);

    const id = Number(dom.editMobileId.value);
    const brand = dom.editBrandInput.value.trim();
    const model = dom.editModelInput.value.trim();
    const priceVal = dom.editPriceInput.value.trim();
    const storage = dom.editStorageInput.value.trim();
    const vendor_id = Number(dom.editVendorSelect.value) || 1;
    const status = dom.editStatusSelect.value;
    const image = dom.editImageInput.value.trim();

    if (!brand) {
      showModalAlert(dom.editModalAlert, 'Brand name is required.');
      dom.editBrandInput.focus();
      return;
    }

    if (!model) {
      showModalAlert(dom.editModalAlert, 'Model name is required.');
      dom.editModelInput.focus();
      return;
    }

    if (!priceVal) {
      showModalAlert(dom.editModalAlert, 'Selling price is required.');
      dom.editPriceInput.focus();
      return;
    }

    const price = Number(priceVal);
    if (isNaN(price)) {
      showModalAlert(dom.editModalAlert, 'Selling price must be a valid number.');
      dom.editPriceInput.focus();
      return;
    }

    if (price < 0) {
      showModalAlert(dom.editModalAlert, 'Price cannot be negative.');
      dom.editPriceInput.focus();
      return;
    }

    setButtonLoading(dom.btnSubmitEditModal, true);

    try {
      const updated = await ApiService.updateProduct(id, {
        brand,
        model,
        price,
        storage,
        status,
        vendor_id,
        image
      });

      closeEditModal();
      showToast('Product Updated', `Details for ID #${id} ("${updated.brand} ${updated.model}") updated in Redis.`, 'success');
      await loadData();

    } catch (err) {
      showModalAlert(dom.editModalAlert, err.message);
      showToast('Error Updating Product', err.message, 'error');
    } finally {
      setButtonLoading(dom.btnSubmitEditModal, false);
    }
  }

  // --- VIEW DETAILS MODAL ---
  function openViewModal(id) {
    const product = state.products.find(m => m.id === Number(id));
    if (!product) return;

    dom.viewProductId.textContent = `#${product.id}`;
    dom.viewProductName.textContent = `${product.brand} ${product.model}`;
    dom.viewProductPrice.textContent = formatINR(product.price);
    dom.viewProductBrand.textContent = product.brand;
    dom.viewProductStorage.textContent = product.storage || '128 GB';
    dom.viewProductVendor.textContent = product.vendor_name || getVendorName(product.vendor_id);
    dom.viewProductUpdated.textContent = formatDate(product.updated_at);

    const statusClass = getStatusClass(product.status, product.price);
    dom.viewProductStatus.textContent = product.status || 'In Stock';
    dom.viewProductStatus.className = `status-badge ${statusClass}`;

    const imgSrc = product.image || resolveImage(product.brand, product.model);
    dom.viewProductImage.src = imgSrc;

    dom.btnViewEditAction.onclick = () => {
      closeViewModal();
      openEditModal(id);
    };

    dom.btnViewDeleteAction.onclick = () => {
      closeViewModal();
      openDeleteModal(id);
    };

    dom.viewMobileModalOverlay.classList.remove('d-none');
  }

  function closeViewModal() {
    dom.viewMobileModalOverlay.classList.add('d-none');
  }

  // --- DELETE CONFIRMATION MODAL ---
  function openDeleteModal(id) {
    state.deletingProductId = id;
    const product = state.products.find(m => m.id === Number(id));
    if (!product) return;

    dom.deleteTargetId.textContent = `#${product.id}`;
    dom.deleteTargetName.textContent = `${product.brand} ${product.model}`;
    dom.deleteTargetPrice.textContent = formatINR(product.price);
    dom.deleteTargetImage.src = product.image || resolveImage(product.brand, product.model);

    dom.deleteModalOverlay.classList.remove('d-none');
  }

  function closeDeleteModal() {
    dom.deleteModalOverlay.classList.add('d-none');
    state.deletingProductId = null;
  }

  async function handleConfirmDelete() {
    const id = state.deletingProductId;
    if (!id) return;

    const product = state.products.find(m => m.id === Number(id));
    const name = product ? `${product.brand} ${product.model}` : `ID #${id}`;

    setButtonLoading(dom.btnConfirmDelete, true);

    try {
      await ApiService.deleteProduct(id);
      closeDeleteModal();
      showToast('Product Removed', `"${name}" (#${id}) was permanently deleted from Redis inventory.`, 'success');
      await loadData();
    } catch (err) {
      showToast('Delete Failed', err.message, 'error');
    } finally {
      setButtonLoading(dom.btnConfirmDelete, false);
    }
  }

  // --- ADD VENDOR MODAL ---
  function openAddVendorModal() {
    hideModalAlert(dom.addVendorModalAlert);
    dom.addVendorForm.reset();
    dom.addVendorModalOverlay.classList.remove('d-none');
    setTimeout(() => dom.addVendorNameInput && dom.addVendorNameInput.focus(), 50);
  }

  function closeAddVendorModal() {
    dom.addVendorModalOverlay.classList.add('d-none');
    hideModalAlert(dom.addVendorModalAlert);
  }

  async function handleAddVendorSubmit(e) {
    e.preventDefault();
    hideModalAlert(dom.addVendorModalAlert);

    const name = dom.addVendorNameInput.value.trim();
    const code = dom.addVendorCodeInput.value.trim();
    const category = dom.addVendorCategoryInput.value.trim();
    const email = dom.addVendorEmailInput.value.trim();
    const phone = dom.addVendorPhoneInput.value.trim();
    const location = dom.addVendorLocationInput.value.trim();

    if (!name) {
      showModalAlert(dom.addVendorModalAlert, 'Vendor name is required.');
      dom.addVendorNameInput.focus();
      return;
    }

    setButtonLoading(dom.btnSubmitAddVendorModal, true);

    try {
      const vendor = await ApiService.createVendor({
        name,
        code,
        category,
        email,
        phone,
        location
      });

      closeAddVendorModal();
      showToast('Vendor Registered', `"${vendor.name}" registered successfully!`, 'success');
      await loadData();
    } catch (err) {
      showModalAlert(dom.addVendorModalAlert, err.message);
      showToast('Error Registering Vendor', err.message, 'error');
    } finally {
      setButtonLoading(dom.btnSubmitAddVendorModal, false);
    }
  }

  // Helper for button loading spinners & duplicate prevention
  function setButtonLoading(btn, loading) {
    if (!btn) return;
    const textSpan = btn.querySelector('.btn-text');
    const spinnerSpan = btn.querySelector('.btn-spinner');

    btn.disabled = loading;
    if (textSpan && spinnerSpan) {
      if (loading) {
        textSpan.classList.add('d-none');
        spinnerSpan.classList.remove('d-none');
      } else {
        textSpan.classList.remove('d-none');
        spinnerSpan.classList.add('d-none');
      }
    }
  }

  // =========================================================================
  // 11. EXPORT PRODUCTS TO CSV (RFC-4180 Compliant)
  // =========================================================================
  function exportProductsCSV() {
    const products = state.filteredProducts.length > 0 ? state.filteredProducts : state.products;
    if (products.length === 0) {
      showToast('Export Unavailable', 'No products available to export.', 'warning');
      return;
    }

    const headers = [
      'Product ID',
      'Brand',
      'Model Name',
      'Storage Capacity',
      'Selling Price (INR)',
      'Stock Status',
      'Vendor ID',
      'Vendor Name',
      'Last Updated'
    ];

    const rows = products.map(p => [
      p.id,
      escapeCSV(p.brand),
      escapeCSV(p.model),
      escapeCSV(p.storage || '128 GB'),
      p.price,
      escapeCSV(p.status || 'In Stock'),
      p.vendor_id || 1,
      escapeCSV(p.vendor_name || getVendorName(p.vendor_id)),
      escapeCSV(p.updated_at || '')
    ]);

    const csvContent = [headers.join(','), ...rows.map(r => r.join(','))].join('\r\n');
    const blob = new Blob([csvContent], { type: 'text/csv;charset=utf-8;' });
    const url = URL.createObjectURL(blob);
    const link = document.createElement('a');
    link.setAttribute('href', url);
    link.setAttribute('download', `coherent_mobiles_products_${new Date().toISOString().slice(0, 10)}.csv`);
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
    URL.revokeObjectURL(url);

    showToast('Export Complete', `Exported ${products.length} products to CSV.`, 'success');
  }

  function escapeCSV(val) {
    if (val === null || val === undefined) return '""';
    const s = String(val).replace(/"/g, '""');
    return `"${s}"`;
  }

  // =========================================================================
  // 12. NAVIGATION & VIEW SWITCHING
  // =========================================================================
  function switchView(viewName) {
    state.activeView = viewName;

    // Update sidebar active link
    dom.navLinks.forEach(link => {
      if (link.dataset.view === viewName) {
        link.classList.add('active');
      } else {
        link.classList.remove('active');
      }
    });

    // Update views visibility
    dom.views.forEach(v => {
      const vId = v.id;
      if (
        (viewName === 'vendors' && vId === 'viewVendors') ||
        (viewName === 'products' && vId === 'viewVendors') ||
        (viewName === 'overview' && vId === 'viewOverview') ||
        (viewName === 'categories' && vId === 'viewCategories') ||
        (viewName === 'inventory' && vId === 'viewInventory') ||
        (viewName === 'orders' && vId === 'viewOrders') ||
        (viewName === 'analytics' && vId === 'viewAnalytics') ||
        (viewName === 'settings' && vId === 'viewSettings')
      ) {
        v.classList.remove('d-none');
      } else {
        v.classList.add('d-none');
      }
    });

    // Update topbar title & breadcrumbs
    const titleMap = {
      vendors: { title: 'Vendor Management & Products List', breadcrumb: 'Dashboard / Vendors' },
      products: { title: 'Smartphone Products List', breadcrumb: 'Dashboard / Products' },
      overview: { title: 'Executive Overview & Telemetry', breadcrumb: 'Dashboard / Overview' },
      categories: { title: 'Device Categories & Series', breadcrumb: 'Dashboard / Categories' },
      inventory: { title: 'Warehouse & Stock Monitoring', breadcrumb: 'Dashboard / Inventory' },
      orders: { title: 'Storefront Orders & Fulfillment', breadcrumb: 'Dashboard / Orders' },
      analytics: { title: 'Portfolio Analytics & Valuation', breadcrumb: 'Dashboard / Analytics' },
      settings: { title: 'System Configuration & Redis Health', breadcrumb: 'Dashboard / Settings' }
    };

    const info = titleMap[viewName] || titleMap.vendors;
    if (dom.topbarTitle) dom.topbarTitle.textContent = info.title;
    if (dom.topbarBreadcrumb) dom.topbarBreadcrumb.textContent = info.breadcrumb;

    if (viewName === 'orders') {
      renderOrdersView();
    }

    // Close mobile sidebar if open
    if (dom.dashSidebar) dom.dashSidebar.classList.remove('open');
    if (dom.sidebarBackdrop) dom.sidebarBackdrop.classList.remove('active');
  }

  // =========================================================================
  // 13. EVENT LISTENERS SETUP
  // =========================================================================
  function setupEventListeners() {
    // Sidebar toggle for mobile/tablet
    if (dom.btnToggleSidebar && dom.dashSidebar && dom.sidebarBackdrop) {
      dom.btnToggleSidebar.addEventListener('click', () => {
        dom.dashSidebar.classList.toggle('open');
        dom.sidebarBackdrop.classList.toggle('active');
      });
      dom.sidebarBackdrop.addEventListener('click', () => {
        dom.dashSidebar.classList.remove('open');
        dom.sidebarBackdrop.classList.remove('active');
      });
    }

    // Sidebar navigation links
    dom.navLinks.forEach(link => {
      link.addEventListener('click', (e) => {
        e.preventDefault();
        const viewName = link.dataset.view;
        switchView(viewName);
      });
    });

    // Retry connection button on banner
    if (dom.btnBannerRetry) {
      dom.btnBannerRetry.addEventListener('click', () => {
        loadData();
      });
    }

    // Top search input
    if (dom.topbarSearchInput) {
      dom.topbarSearchInput.addEventListener('input', (e) => {
        state.searchQuery = e.target.value;
        if (dom.tableSearchInput) dom.tableSearchInput.value = state.searchQuery;
        if (dom.btnClearSearch) {
          dom.btnClearSearch.classList.toggle('d-none', !state.searchQuery);
        }
        state.pagination.currentPage = 1;
        applyFiltersAndSort();
      });
    }

    // Table search input
    if (dom.tableSearchInput) {
      dom.tableSearchInput.addEventListener('input', (e) => {
        state.searchQuery = e.target.value;
        if (dom.topbarSearchInput) dom.topbarSearchInput.value = state.searchQuery;
        if (dom.btnClearSearch) {
          dom.btnClearSearch.classList.toggle('d-none', !state.searchQuery);
        }
        state.pagination.currentPage = 1;
        applyFiltersAndSort();
      });
    }

    // Clear search button
    if (dom.btnClearSearch) {
      dom.btnClearSearch.addEventListener('click', () => {
        state.searchQuery = '';
        if (dom.tableSearchInput) dom.tableSearchInput.value = '';
        if (dom.topbarSearchInput) dom.topbarSearchInput.value = '';
        dom.btnClearSearch.classList.add('d-none');
        state.pagination.currentPage = 1;
        applyFiltersAndSort();
      });
    }

    // Brand filter select
    if (dom.brandSelectFilter) {
      dom.brandSelectFilter.addEventListener('change', (e) => {
        state.brandFilter = e.target.value;
        populateBrandFilters(); // updates active chip
        state.pagination.currentPage = 1;
        applyFiltersAndSort();
      });
    }

    // Status filter select
    if (dom.statusSelectFilter) {
      dom.statusSelectFilter.addEventListener('change', (e) => {
        state.statusFilter = e.target.value;
        state.pagination.currentPage = 1;
        applyFiltersAndSort();
      });
    }

    // Sort select
    if (dom.sortSelectFilter) {
      dom.sortSelectFilter.addEventListener('change', (e) => {
        state.sortBy = e.target.value;
        applyFiltersAndSort();
      });
    }

    // View Switcher (Table vs Grid)
    if (dom.btnViewTable && dom.btnViewCards) {
      dom.btnViewTable.addEventListener('click', () => {
        state.viewMode = 'table';
        dom.btnViewTable.classList.add('active');
        dom.btnViewCards.classList.remove('active');
        renderProductsDisplay();
      });
      dom.btnViewCards.addEventListener('click', () => {
        state.viewMode = 'cards';
        dom.btnViewCards.classList.add('active');
        dom.btnViewTable.classList.remove('active');
        renderProductsDisplay();
      });
    }

    // Export CSV
    if (dom.btnExportCSV) {
      dom.btnExportCSV.addEventListener('click', exportProductsCSV);
    }

    // Refresh button
    if (dom.btnRefresh) {
      dom.btnRefresh.addEventListener('click', async () => {
        await loadData();
        showToast('Refreshed', 'Inventory records synced from Redis.', 'info');
      });
    }

    // Reset Defaults button
    if (dom.btnResetData) {
      dom.btnResetData.addEventListener('click', async () => {
        if (confirm('Reset Redis inventory and vendors back to the default CoherentMobiles sample catalogue?')) {
          try {
            await ApiService.resetData();
            showToast('Catalogue Reset', 'Redis restored to original CoherentMobiles seed data.', 'success');
            await loadData();
          } catch (err) {
            showToast('Reset Failed', err.message, 'error');
          }
        }
      });
    }

    // Clear vendor filter in strip
    if (dom.btnClearVendorFilter) {
      dom.btnClearVendorFilter.addEventListener('click', () => {
        state.activeVendorFilter = null;
        renderVendorPills();
        updateSelectedVendorStrip();
        applyFiltersAndSort();
      });
    }

    // Empty state buttons
    if (dom.btnEmptyResetFilters) {
      dom.btnEmptyResetFilters.addEventListener('click', () => {
        state.searchQuery = '';
        state.brandFilter = '';
        state.statusFilter = '';
        state.activeVendorFilter = null;
        if (dom.tableSearchInput) dom.tableSearchInput.value = '';
        if (dom.topbarSearchInput) dom.topbarSearchInput.value = '';
        if (dom.brandSelectFilter) dom.brandSelectFilter.value = '';
        if (dom.statusSelectFilter) dom.statusSelectFilter.value = '';
        renderVendorPills();
        applyFiltersAndSort();
      });
    }

    if (dom.btnEmptyAdd) {
      dom.btnEmptyAdd.addEventListener('click', openAddModal);
    }

    // Pagination controls
    if (dom.pageSizeSelect) {
      dom.pageSizeSelect.addEventListener('change', (e) => {
        state.pagination.pageSize = Number(e.target.value);
        state.pagination.currentPage = 1;
        applyFiltersAndSort();
      });
    }

    if (dom.btnPrevPage) {
      dom.btnPrevPage.addEventListener('click', () => {
        if (state.pagination.currentPage > 1) {
          state.pagination.currentPage--;
          renderProductsDisplay();
          renderPagination();
        }
      });
    }

    if (dom.btnNextPage) {
      dom.btnNextPage.addEventListener('click', () => {
        if (state.pagination.currentPage < state.pagination.totalPages) {
          state.pagination.currentPage++;
          renderProductsDisplay();
          renderPagination();
        }
      });
    }

    // Add Product Modal triggers
    if (dom.btnOpenAddModal) dom.btnOpenAddModal.addEventListener('click', openAddModal);
    if (dom.btnOpenAddModalToolbar) dom.btnOpenAddModalToolbar.addEventListener('click', openAddModal);
    if (dom.btnCloseAddModal) dom.btnCloseAddModal.addEventListener('click', closeAddModal);
    if (dom.btnCancelAddModal) dom.btnCancelAddModal.addEventListener('click', closeAddModal);
    if (dom.addMobileForm) dom.addMobileForm.addEventListener('submit', handleAddSubmit);

    // Live preview updates on Add Modal
    ['input', 'change'].forEach(evt => {
      [dom.addBrandInput, dom.addModelInput, dom.addPriceInput, dom.addStorageInput, dom.addVendorSelect, dom.addStatusSelect, dom.addImageInput].forEach(el => {
        if (el) el.addEventListener(evt, updateAddPreview);
      });
    });

    // Quick chips on Add Modal
    const chips = document.querySelectorAll('.quick-chip[data-brand]');
    chips.forEach(chip => {
      chip.addEventListener('click', () => {
        if (dom.addBrandInput) {
          dom.addBrandInput.value = chip.dataset.brand;
          updateAddPreview();
          if (dom.addModelInput) dom.addModelInput.focus();
        }
      });
    });

    // Edit Product Modal triggers
    if (dom.btnCloseEditModal) dom.btnCloseEditModal.addEventListener('click', closeEditModal);
    if (dom.btnCancelEditModal) dom.btnCancelEditModal.addEventListener('click', closeEditModal);
    if (dom.editMobileForm) dom.editMobileForm.addEventListener('submit', handleEditSubmit);

    // Live preview updates on Edit Modal
    ['input', 'change'].forEach(evt => {
      [dom.editBrandInput, dom.editModelInput, dom.editPriceInput, dom.editStorageInput, dom.editVendorSelect, dom.editStatusSelect, dom.editImageInput].forEach(el => {
        if (el) el.addEventListener(evt, updateEditPreview);
      });
    });

    // View Modal triggers
    if (dom.btnCloseViewModal) dom.btnCloseViewModal.addEventListener('click', closeViewModal);

    // Delete Modal triggers
    if (dom.btnCloseDeleteModal) dom.btnCloseDeleteModal.addEventListener('click', closeDeleteModal);
    if (dom.btnCancelDeleteModal) dom.btnCancelDeleteModal.addEventListener('click', closeDeleteModal);
    if (dom.btnConfirmDelete) dom.btnConfirmDelete.addEventListener('click', handleConfirmDelete);

    // Add Vendor Modal triggers
    if (dom.btnOpenAddVendorModal) dom.btnOpenAddVendorModal.addEventListener('click', openAddVendorModal);
    if (dom.btnCloseAddVendorModal) dom.btnCloseAddVendorModal.addEventListener('click', closeAddVendorModal);
    if (dom.btnCancelAddVendorModal) dom.btnCancelAddVendorModal.addEventListener('click', closeAddVendorModal);
    if (dom.addVendorForm) dom.addVendorForm.addEventListener('submit', handleAddVendorSubmit);

    // Notification dropdown toggle
    if (dom.notifBellBtn && dom.notifDropdown) {
      dom.notifBellBtn.addEventListener('click', (e) => {
        e.stopPropagation();
        dom.notifDropdown.classList.toggle('d-none');
      });
      document.addEventListener('click', () => {
        if (dom.notifDropdown) dom.notifDropdown.classList.add('d-none');
      });
      dom.notifDropdown.addEventListener('click', (e) => e.stopPropagation());
    }

    // Go to Analytics shortcut
    if (dom.btnGoToAnalytics) {
      dom.btnGoToAnalytics.addEventListener('click', () => switchView('analytics'));
    }

    // Keyboard shortcut (Ctrl+K or Cmd+K) to focus search
    document.addEventListener('keydown', (e) => {
      if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === 'k') {
        e.preventDefault();
        if (dom.topbarSearchInput) dom.topbarSearchInput.focus();
      }
      if (e.key === 'Escape') {
        closeAddModal();
        closeEditModal();
        closeViewModal();
        closeDeleteModal();
        closeAddVendorModal();
      }
    });
  }

  // =========================================================================
  // 14. INITIALIZATION
  // =========================================================================
  document.addEventListener('DOMContentLoaded', () => {
    setupEventListeners();
    switchView('vendors'); // Default to Vendor Management view
    loadData();
  });

})();
