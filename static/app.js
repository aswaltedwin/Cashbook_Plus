const state = {
	username: "",
	activeCashbook: "",
	allEntries: [],
	summary: { total_in: 0, total_out: 0, balance: 0 },
};

const toastContainer = document.getElementById("toast-container");
const loadingOverlay = document.getElementById("loading-overlay");

function showToast(message, type = "info") {
	if (!toastContainer) return;
	const toast = document.createElement("div");
	toast.className = `toast ${type}`;
	toast.textContent = message;
	toastContainer.appendChild(toast);
	requestAnimationFrame(() => toast.classList.add("visible"));
	setTimeout(() => {
		toast.classList.remove("visible");
		setTimeout(() => toast.remove(), 320);
	}, 3600);
}

function showLoading(active) {
	if (!loadingOverlay) return;
	if (active) {
		loadingOverlay.classList.add("active");
	} else {
		loadingOverlay.classList.remove("active");
	}
}

async function fetchJSON(url, options = {}) {
	const response = await fetch(url, {
		headers: { "Content-Type": "application/json", ...(options.headers || {}) },
		...options,
	});
	if (response.status === 401) {
		window.location.href = "/login";
		return Promise.reject(new Error("Unauthorized"));
	}
	if (!response.ok) {
		const payload = await response.json().catch(() => ({}));
		throw new Error(payload.detail || payload.message || "Request failed");
	}
	return response.json();
}

function getCashbookFromURL() {
	const params = new URLSearchParams(window.location.search);
	return params.get("cashbook") || "";
}

function updateCashbookIndicator() {
	const indicator = document.getElementById("cashbook-indicator");
	const nameEl = document.getElementById("active-cashbook-name");
	if (indicator && nameEl) {
		if (state.activeCashbook) {
			indicator.style.display = "flex";
			nameEl.textContent = state.activeCashbook;
		} else {
			indicator.style.display = "none";
		}
	}
}

function formatCurrency(amount) {
	return new Intl.NumberFormat("en-IN", {
		style: "currency",
		currency: "INR",
		maximumFractionDigits: 2,
	}).format(Number(amount || 0));
}

function animateValue(element, start, end, duration = 600) {
	const diff = end - start;
	if (diff === 0) {
		element.textContent = formatCurrency(end);
		return;
	}
	const steps = Math.max(16, Math.floor(duration / 16));
	let currentStep = 0;
	const stepValue = diff / steps;
	const timer = setInterval(() => {
		currentStep += 1;
		const value = currentStep >= steps ? end : start + stepValue * currentStep;
		element.textContent = formatCurrency(value);
		if (currentStep >= steps) {
			clearInterval(timer);
		}
	}, 16);
}

function updateSummaryCards(summary) {
	const totalInEl = document.getElementById("total-in");
	const totalOutEl = document.getElementById("total-out");
	const balanceEl = document.getElementById("balance");
	if (!totalInEl || !totalOutEl || !balanceEl) return;
	animateValue(totalInEl, state.summary.total_in, summary.total_in);
	animateValue(totalOutEl, state.summary.total_out, summary.total_out);
	animateValue(balanceEl, state.summary.balance, summary.balance);
	state.summary = summary;
}

function applyFilters() {
	const keywordInput = document.getElementById("search-input");
	const dateInput = document.getElementById("date-filter");
	const keyword = (keywordInput?.value || "").trim().toLowerCase();
	const dateFilter = dateInput?.value || "";
	let filtered = [...state.allEntries];
	if (keyword) {
		filtered = filtered.filter((entry) => {
			return (
				String(entry.note || "").toLowerCase().includes(keyword) ||
				String(entry.amount).includes(keyword)
			);
		});
	}
	if (dateFilter) {
		filtered = filtered.filter((entry) => entry.date === dateFilter);
	}
	renderEntries(filtered);
}

function renderEntries(entries = []) {
	const tbody = document.getElementById("transaction-body");
	const countEl = document.getElementById("entry-count");
	if (!tbody) return;
	tbody.innerHTML = "";
	if (entries.length === 0) {
		const row = document.createElement("tr");
		const cell = document.createElement("td");
		cell.colSpan = 5;
		cell.className = "empty-state";
		cell.textContent = "No transactions found. Add your first entry!";
		row.appendChild(cell);
		tbody.appendChild(row);
		countEl && (countEl.textContent = "0 entries");
		updateInsights([]);
		return;
	}
	entries
		.slice()
		.sort((a, b) => new Date(b.date) - new Date(a.date))
		.forEach((entry) => {
			const row = document.createElement("tr");
			row.setAttribute("data-type", entry.type);
			row.innerHTML = `
				<td>${entry.date}</td>
				<td>${entry.type === "cash_in" ? "Cash In" : "Cash Out"}</td>
				<td>${formatCurrency(entry.amount)}</td>
				<td>${entry.note || "—"}</td>
				<td>
					<button class="btn ghost" data-delete="${entry.id}">Delete</button>
				</td>
			`;
			tbody.appendChild(row);
		});
	countEl && (countEl.textContent = `${entries.length} ${entries.length === 1 ? "entry" : "entries"}`);
	updateInsights(entries);
}

function updateInsights(entries) {
	const insightsList = document.getElementById("insights-list");
	if (!insightsList) return;
	insightsList.innerHTML = "";
	if (!entries || entries.length === 0) {
		const item = document.createElement("li");
		item.textContent = "Keep logging entries to unlock smart insights! 📈";
		insightsList.appendChild(item);
		return;
	}

	const totalIn = entries.filter((e) => e.type === "cash_in").reduce((sum, e) => sum + Number(e.amount), 0);
	const totalOut = entries.filter((e) => e.type === "cash_out").reduce((sum, e) => sum + Number(e.amount), 0);

	const now = new Date();
	const sevenDaysAgo = new Date(now);
	sevenDaysAgo.setDate(now.getDate() - 7);
	const fourteenDaysAgo = new Date(now);
	fourteenDaysAgo.setDate(now.getDate() - 14);

	const spendLastWeek = entries
		.filter((e) => e.type === "cash_out" && new Date(e.date) >= sevenDaysAgo)
		.reduce((sum, e) => sum + Number(e.amount), 0);
	const spendPrevWeek = entries
		.filter((e) => e.type === "cash_out" && new Date(e.date) < sevenDaysAgo && new Date(e.date) >= fourteenDaysAgo)
		.reduce((sum, e) => sum + Number(e.amount), 0);

	const insights = [];
	if (totalOut > 0) {
		insights.push(`Spending totals ${formatCurrency(totalOut)} so far.`);
	}
	if (totalIn > 0) {
		insights.push(`You have logged ${formatCurrency(totalIn)} in cash inflows.`);
	}
	if (spendPrevWeek > 0) {
		const diff = spendLastWeek - spendPrevWeek;
		const percentage = (diff / spendPrevWeek) * 100;
		if (Math.abs(percentage) >= 10) {
			const direction = percentage > 0 ? "more" : "less";
			insights.push(`You spent ${Math.abs(percentage).toFixed(1)}% ${direction} this week compared to last.`);
		}
	} else if (spendLastWeek > 0) {
		insights.push("New spending appeared this week. Track recurring expenses for better planning.");
	}

	const topNotes = entries
		.filter((e) => e.type === "cash_out" && e.note)
		.reduce((acc, entry) => {
			const key = entry.note.trim().toLowerCase();
			acc[key] = (acc[key] || 0) + Number(entry.amount);
			return acc;
		}, {});
	const sortedNotes = Object.entries(topNotes).sort((a, b) => b[1] - a[1]);
	if (sortedNotes.length > 0) {
		const [note, amount] = sortedNotes[0];
		insights.push(`Top spending note: "${note}" (${formatCurrency(amount)}).`);
	}

	if (state.summary.balance < 0) {
		insights.push("Balance is negative. Consider reducing expenses or increasing income.");
	}

	if (insights.length === 0) {
		insights.push("Your cash flow is steady. Keep logging data for deeper insights!");
	}

	insights.forEach((text) => {
		const item = document.createElement("li");
		item.textContent = text;
		insightsList.appendChild(item);
	});
}

async function loadEntries() {
	if (!state.activeCashbook) {
		renderEntries([]);
		updateSummaryCards({ total_in: 0, total_out: 0, balance: 0 });
		return;
	}
	showLoading(true);
	try {
		const entriesResponse = await fetchJSON(`/api/get_entries?cashbook=${encodeURIComponent(state.activeCashbook)}`);
		state.allEntries = entriesResponse.entries || [];

		// ✅ Save entries locally for export
		localStorage.setItem(`transactions_${state.activeCashbook}`, JSON.stringify(state.allEntries));

		const summary = await fetchJSON(`/api/summary/${encodeURIComponent(state.activeCashbook)}`);
		updateSummaryCards(summary);
		renderEntries(state.allEntries);
	} catch (error) {
		showToast(error.message, "error");
	} finally {
		showLoading(false);
	}
}


async function loadCashbooks() {
	showLoading(true);
	try {
		const data = await fetchJSON("/api/get_cashbooks");
		if (data.username) {
			state.username = data.username;
			const welcomeEl = document.getElementById("welcome-user");
			if (welcomeEl) {
				welcomeEl.textContent = `Hi, ${state.username}!`;
			}
		}
		const cashbooks = data.cashbooks || [];
		const urlCashbook = getCashbookFromURL();
		if (urlCashbook && cashbooks.includes(urlCashbook)) {
			state.activeCashbook = urlCashbook;
		} else if (cashbooks.length > 0 && !state.activeCashbook) {
			state.activeCashbook = cashbooks[0];
		} else if (cashbooks.length === 0) {
			state.activeCashbook = "";
		}
		updateCashbookIndicator();
		await loadEntries();
	} catch (error) {
		showToast(error.message, "error");
	} finally {
		showLoading(false);
	}
}

function handleThemeInitialization() {
	const saved = localStorage.getItem("cb_theme");
	const prefersDark = window.matchMedia && window.matchMedia("(prefers-color-scheme: dark)").matches;
	const theme = saved || (prefersDark ? "dark" : "light");
	setTheme(theme);
	const toggleBtn = document.getElementById("theme-toggle");
	if (toggleBtn) {
		toggleBtn.addEventListener("click", () => {
			const newTheme = document.body.classList.contains("theme-dark") ? "light" : "dark";
			setTheme(newTheme);
		});
	}
}

function setTheme(theme) {
	document.body.classList.remove("theme-light", "theme-dark");
	document.body.classList.add(theme === "dark" ? "theme-dark" : "theme-light");
	const toggleBtn = document.getElementById("theme-toggle");
	if (toggleBtn) {
		toggleBtn.textContent = theme === "dark" ? "☀️" : "🌙";
	}
	localStorage.setItem("cb_theme", theme);
}

function bindEvents() {
	const entryForm = document.getElementById("entry-form");
	if (entryForm) {
		entryForm.addEventListener("submit", async (event) => {
			event.preventDefault();
			if (!state.activeCashbook) {
				showToast("Please select a cashbook from the Cashbooks page first", "info");
				window.location.href = "/cashbooks";
				return;
			}
			const formData = new FormData(entryForm);
			const payload = Object.fromEntries(formData.entries());
			payload.cashbook = state.activeCashbook;
			try {
				await fetchJSON("/api/add_entry", {
					method: "POST",
					body: JSON.stringify(payload),
				});
				showToast("Entry added", "success");
				entryForm.reset();
				await loadEntries();
			} catch (error) {
				showToast(error.message, "error");
			}
		});
	}

	const table = document.getElementById("transaction-body");
	if (table) {
		table.addEventListener("click", async (event) => {
			const target = event.target;
			if (target && target.dataset && target.dataset.delete) {
				if (!state.activeCashbook) {
					showToast("No cashbook selected", "info");
					return;
				}
				const entryId = target.dataset.delete;
				try {
					await fetchJSON(`/api/delete_entry/${entryId}?cashbook=${encodeURIComponent(state.activeCashbook)}`, {
						method: "DELETE",
					});
					showToast("Entry deleted", "success");
					await loadEntries();
				} catch (error) {
					showToast(error.message, "error");
				}
			}
		});
	}

	const searchInput = document.getElementById("search-input");
	const dateFilter = document.getElementById("date-filter");
	const clearFilters = document.getElementById("clear-filters");
	searchInput && searchInput.addEventListener("input", applyFilters);
	dateFilter && dateFilter.addEventListener("input", applyFilters);
	clearFilters &&
		clearFilters.addEventListener("click", () => {
			if (searchInput) searchInput.value = "";
			if (dateFilter) dateFilter.value = "";
			applyFilters();
		});

	// PDF Export only
	const exportPDF = document.getElementById("export-pdf");
	if (exportPDF) {
		exportPDF.addEventListener("click", async () => {
			if (!state.activeCashbook) {
				showToast("Select a cashbook to export.", "info");
				return;
			}
			await exportPDFOnly(state.activeCashbook);
		});
	}

	// Excel Export only
	const exportExcel = document.getElementById("export-excel");
	if (exportExcel) {
		exportExcel.addEventListener("click", async () => {
			if (!state.activeCashbook) {
				showToast("Select a cashbook to export.", "info");
				return;
			}
			await exportExcelOnly(state.activeCashbook);
		});
	}

	
	const logoutBtn = document.getElementById("logout-btn");
	if (logoutBtn) {
		logoutBtn.addEventListener("click", async () => {
			try {
				await fetchJSON("/api/logout", { method: "POST" });
			} finally {
				window.location.href = "/login";
			}
		});
	}
}

// 🧾 Export filtered data as PDF or Excel
async function exportPDFOnly(cashbook) {
	const entries = state.allEntries || [];
	if (!entries.length) return showToast("No data to export.", "info");

	const { jsPDF } = window.jspdf;
	const doc = new jsPDF();
	doc.setFont("helvetica", "normal");
	doc.setFontSize(14);
	doc.text(`CashBook+ Transactions`, 14, 20);
	doc.setFontSize(11);
	doc.text(`Cashbook: ${cashbook}`, 14, 28);
	doc.text(`Exported on: ${new Date().toLocaleDateString()}`, 140, 28);

	const rows = entries
		.slice()
		.sort((a, b) => new Date(b.date) - new Date(a.date))
		.map((t, i) => [
			(i + 1).toString(),
			t.date,
			t.type === "cash_in" ? "Cash In" : "Cash Out",
			t.amount.toFixed(2),
			t.note || "-"
		]);

	const totalIn = entries.filter(t => t.type === "cash_in").reduce((sum, t) => sum + t.amount, 0);
	const totalOut = entries.filter(t => t.type === "cash_out").reduce((sum, t) => sum + t.amount, 0);
	const balance = totalIn - totalOut;

	doc.autoTable({
		head: [["#", "Date", "Type", "Amount", "Note"]],
		body: rows,
		startY: 36,
		theme: "grid",
		headStyles: { fillColor: [41, 128, 185], textColor: 255 },
		styles: { fontSize: 10, cellPadding: 3 },
	});

	let finalY = doc.lastAutoTable.finalY + 8;
	doc.setFontSize(11);
	doc.setFont("helvetica", "bold");
	doc.text(`Total Cash In: ${totalIn.toFixed(2)}`, 14, finalY);
	doc.text(`Total Cash Out: ${totalOut.toFixed(2)}`, 14, finalY + 6);
	doc.text(`Balance: ${balance.toFixed(2)}`, 14, finalY + 12);

	doc.save(`${cashbook}-transactions.pdf`);
	showToast("PDF exported successfully!", "success");
}

async function exportExcelOnly(cashbook) {
	const entries = state.allEntries || [];
	if (!entries.length) return showToast("No data to export.", "info");

	const rows = entries
		.slice()
		.sort((a, b) => new Date(b.date) - new Date(a.date))
		.map((t, i) => [
			(i + 1).toString(),
			t.date,
			t.type === "cash_in" ? "Cash In" : "Cash Out",
			t.amount.toFixed(2),
			t.note || "-"
		]);

	const totalIn = entries.filter(t => t.type === "cash_in").reduce((sum, t) => sum + t.amount, 0);
	const totalOut = entries.filter(t => t.type === "cash_out").reduce((sum, t) => sum + t.amount, 0);
	const balance = totalIn - totalOut;

	const worksheetData = [
		["#", "Date", "Type", "Amount", "Note"],
		...rows,
		[],
		["", "", "Total Cash In", totalIn.toFixed(2)],
		["", "", "Total Cash Out", totalOut.toFixed(2)],
		["", "", "Balance", balance.toFixed(2)]
	];

	const workbook = XLSX.utils.book_new();
	const worksheet = XLSX.utils.aoa_to_sheet(worksheetData);
	XLSX.utils.book_append_sheet(workbook, worksheet, "Transactions");
	XLSX.writeFile(workbook, `${cashbook}-transactions.xlsx`);

	showToast("Excel exported successfully!", "success");
}




// Event Listeners
document.getElementById("export-pdf")?.addEventListener("click", () => exportData("pdf"));
document.getElementById("export-excel")?.addEventListener("click", () => exportData("excel"));


document.addEventListener("DOMContentLoaded", async () => {
	if (!document.getElementById("entry-form")) return;
	handleThemeInitialization();
	bindEvents();
	await loadCashbooks();
	showLoading(false);
});

