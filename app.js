const pagesByPath = new Map([
	["/", "home"],
	["/index.html", "home"],
	["/dashboard", "dashboard"],
	["/tasks", "tasks"],
	["/services", "services"],
	["/projects", "projects"],
	["/admin", "admin"],
	["/access", "access"],
	["/login", "login"],
	["/register", "register"],
]);

const protectedPages = new Set(["tasks", "projects", "admin"]);
const contractStatuses = ["Solicitado", "Em andamento", "Concluído", "Cancelado"];
const svgNamespace = "http://www.w3.org/2000/svg";
let currentUser;
let pendingPath = "/projects";

const appStatus = document.querySelector("#app-status");
const accountEmail = document.querySelector("#account-email");
const loginLink = document.querySelector("#login-link");
const logoutButton = document.querySelector("#logout-button");
const adminLink = document.querySelector("#admin-link");
const ownerServicesCard = document.querySelector("#owner-services-card");

function setGlobalStatus(message = "") {
	appStatus.textContent = message;
	appStatus.hidden = message.length === 0;
}

function updateAccountControls() {
	const isSignedIn = Boolean(currentUser);
	accountEmail.textContent = isSignedIn ? currentUser.email : "";
	accountEmail.hidden = !isSignedIn;
	loginLink.hidden = isSignedIn;
	logoutButton.hidden = !isSignedIn;
	const isOwner = currentUser?.role === "owner";
	adminLink.hidden = !isOwner;
	ownerServicesCard.hidden = !isOwner;
}

async function requestJson(path, options = {}) {
	const response = await fetch(path, {
		...options,
		credentials: "same-origin",
		headers: {
			...(options.body ? { "Content-Type": "application/json" } : {}),
			...options.headers,
		},
	});

	const responseText = await response.text();
	let payload;
	try {
		payload = JSON.parse(responseText);
	} catch {
		throw new Error("O servidor retornou uma resposta inválida. Confira se ele está em execução.");
	}

	if (!response.ok) {
		const error = new Error(payload.error || "Não foi possível concluir a solicitação.");
		error.status = response.status;
		throw error;
	}
	return payload;
}

async function refreshSession() {
	const result = await requestJson("/api/session");
	currentUser = result.user;
	updateAccountControls();
	return currentUser;
}

function activePage(pageName) {
	document.querySelectorAll("[data-page]").forEach((page) => {
		page.hidden = page.dataset.page !== pageName;
	});
}

function pageTitle(pageName) {
	const titles = {
		home: "Felipe — Desenvolvedor Web",
		dashboard: "Dashboard de vendas — Felipe",
		tasks: "Painel de tarefas — Felipe",
		services: "Serviços — Felipe",
		projects: "Projetos disponíveis — Felipe",
		admin: "Gestão de solicitações — Felipe",
		access: "Acesso do cliente — Felipe",
		login: "Entrar — Felipe",
		register: "Cadastro — Felipe",
	};
	document.title = titles[pageName] || titles.home;
}

async function renderRoute() {
	const requestedPath = window.location.pathname;
	const pageName = pagesByPath.get(requestedPath) || "home";

	if (protectedPages.has(pageName)) {
		pendingPath = requestedPath;
		try {
			await refreshSession();
		} catch (error) {
			setGlobalStatus(error.message);
			activePage("access");
			pageTitle("access");
			return;
		}

		if (!currentUser) {
			activePage("access");
			pageTitle("access");
			return;
		}
		if (pageName === "admin" && currentUser.role !== "owner") {
			window.history.replaceState({}, "", "/");
			activePage("home");
			pageTitle("home");
			setGlobalStatus("Esta área é restrita ao responsável pelo projeto.");
			return;
		}
	}

	if (pageName === "access" || pageName === "login" || pageName === "register") {
		try {
			await refreshSession();
		} catch (error) {
			setGlobalStatus(error.message);
		}
	}

	activePage(pageName);
	pageTitle(pageName);
	setGlobalStatus("");

	if (pageName === "dashboard") {
		await loadDashboard();
	} else if (pageName === "tasks") {
		await loadTasks();
	} else if (pageName === "services" || pageName === "projects") {
		await loadServices();
	} else if (pageName === "admin") {
		await loadAdminContracts();
	}
}

function navigate(path, replace = false) {
	if (replace) {
		window.history.replaceState({}, "", path);
	} else if (window.location.pathname !== path) {
		window.history.pushState({}, "", path);
	}
	return renderRoute();
}

document.addEventListener("click", (event) => {
	const routeLink = event.target.closest("a[data-route]");
	if (!routeLink || event.defaultPrevented || event.button !== 0) {
		return;
	}
	if (event.metaKey || event.ctrlKey || event.shiftKey || event.altKey) {
		return;
	}

	event.preventDefault();
	navigate(routeLink.pathname);
});

window.addEventListener("popstate", renderRoute);

function svgElement(name, attributes = {}) {
	const element = document.createElementNS(svgNamespace, name);
	Object.entries(attributes).forEach(([attribute, value]) => {
		element.setAttribute(attribute, String(value));
	});
	return element;
}

function drawSalesChart(series) {
	const chart = document.querySelector("#sales-chart");
	const labels = document.querySelector("#chart-months");
	chart.replaceChildren();
	labels.replaceChildren();

	const width = 720;
	const height = 280;
	const left = 46;
	const right = 12;
	const top = 18;
	const bottom = 252;
	const maxValue = Math.max(1, ...series.map((item) => item.count));
	const stepX = (width - left - right) / Math.max(series.length - 1, 1);
	const points = series.map((item, index) => ({
		x: left + index * stepX,
		y: bottom - (item.count / maxValue) * (bottom - top),
		item,
	}));

	const definitions = svgElement("defs");
	const gradient = svgElement("linearGradient", {
		id: "chart-fill",
		x1: "0",
		x2: "0",
		y1: "0",
		y2: "1",
	});
	gradient.append(
		svgElement("stop", {
			offset: "0%",
			"stop-color": "#b69cff",
			"stop-opacity": ".28",
		}),
		svgElement("stop", {
			offset: "100%",
			"stop-color": "#b69cff",
			"stop-opacity": "0",
		}),
	);
	definitions.append(gradient);
	chart.append(definitions);

	for (let index = 0; index <= 4; index += 1) {
		const y = top + ((bottom - top) * index) / 4;
		const value = Math.round(maxValue * (1 - index / 4));
		chart.append(
			svgElement("line", {
				x1: left,
				y1: y,
				x2: width - right,
				y2: y,
				class: "chart-grid-line",
			}),
		);
		const label = svgElement("text", {
			x: left - 10,
			y: y + 4,
			"dominant-baseline": "middle",
			"text-anchor": "end",
			class: "chart-axis-label",
		});
		label.textContent = String(value);
		chart.append(label);
	}

	const linePath = points
		.map((point, index) => `${index === 0 ? "M" : "L"} ${point.x} ${point.y}`)
		.join(" ");
	const areaPath = `${linePath} L ${points.at(-1).x} ${bottom} L ${points[0].x} ${bottom} Z`;
	chart.append(
		svgElement("path", { d: areaPath, class: "chart-area" }),
		svgElement("path", { d: linePath, class: "chart-line" }),
	);

	points.forEach((point) => {
		const circle = svgElement("circle", {
			cx: point.x,
			cy: point.y,
			r: 5,
			class: "chart-point",
		});
		const tooltip = svgElement("title");
		tooltip.textContent = `${point.item.label}: ${point.item.count} solicitações`;
		circle.append(tooltip);
		chart.append(circle);

		const monthLabel = document.createElement("span");
		monthLabel.textContent = point.item.label;
		labels.append(monthLabel);
	});
}

async function loadDashboard() {
	const message = document.querySelector("#chart-message");
	document.querySelector("#stat-total").textContent = "—";
	document.querySelector("#stat-month").textContent = "—";
	document.querySelector("#stat-services").textContent = "—";
	message.textContent = "Carregando dados...";

	try {
		const data = await requestJson("/api/dashboard");
		document.querySelector("#stat-total").textContent = String(data.total);
		document.querySelector("#stat-month").textContent = String(data.this_month);
		document.querySelector("#stat-services").textContent = String(data.service_count);
		drawSalesChart(data.series);
		message.textContent = data.total === 0
			? "Ainda não há solicitações registradas. O gráfico será atualizado quando um cliente enviar um pedido."
			: "";
	} catch (error) {
		message.textContent = error.message;
	}
}

function makeElement(tagName, className, text) {
	const element = document.createElement(tagName);
	if (className) {
		element.className = className;
	}
	if (text !== undefined) {
		element.textContent = text;
	}
	return element;
}

function renderOfferings(container, services) {
	container.replaceChildren();
	if (services.length === 0) {
		container.append(makeElement("p", "empty-state", "Nenhum serviço está disponível no momento."));
		return;
	}

	services.forEach((service, index) => {
		const card = makeElement("article", "offer-card");
		const category = makeElement("span", "category", service.category);
		const heading = makeElement("h2", "", service.title);
		const description = makeElement("p", "", service.description);
		const form = makeElement("form", "service-form");
		form.dataset.serviceForm = "";
		form.dataset.serviceId = service.id;

		const labelId = `service-description-${index}`;
		const label = makeElement("label", "", "Conte um pouco sobre o que precisa (opcional)");
		label.htmlFor = labelId;
		const textarea = document.createElement("textarea");
		textarea.id = labelId;
		textarea.name = "description";
		textarea.maxLength = 2000;
		textarea.rows = 3;
		textarea.placeholder = "Descreva sua ideia ou necessidade";

		const button = makeElement("button", "button primary", "Solicitar contratação");
		button.type = "submit";
		const message = makeElement("p", "service-message");
		message.setAttribute("role", "status");

		form.append(label, textarea, button, message);
		card.append(category, heading, description, form);
		container.append(card);
	});
}

async function loadServices() {
	const containers = [
		document.querySelector("#service-catalog"),
		document.querySelector("#project-catalog"),
	];
	containers.forEach((container) => {
		container.replaceChildren(makeElement("p", "empty-state", "Carregando catálogo..."));
	});

	try {
		const result = await requestJson("/api/services");
		containers.forEach((container) => renderOfferings(container, result.services));
	} catch (error) {
		containers.forEach((container) => {
			container.replaceChildren(makeElement("p", "empty-state", error.message));
		});
	}
}

function renderTasks(contracts) {
	const container = document.querySelector("#tasks-list");
	container.replaceChildren();
	if (contracts.length === 0) {
		const emptyState = makeElement(
			"p",
			"empty-state",
			"Você ainda não tem serviços contratados. Visite o catálogo para enviar uma solicitação.",
		);
		const catalogLink = makeElement("a", "text-link", "Ver catálogo de serviços");
		catalogLink.href = "/services";
		catalogLink.dataset.route = "";
		emptyState.append(" ", catalogLink);
		container.append(emptyState);
		return;
	}

	contracts.forEach((contract) => {
		const card = makeElement("article", "record-card");
		const header = makeElement("div", "record-heading");
		const titleBlock = document.createElement("div");
		titleBlock.append(makeElement("h2", "", contract.service_title));
		const createdAt = new Date(contract.created_at);
		titleBlock.append(
			makeElement(
				"span",
				"record-date",
				`Solicitado em ${createdAt.toLocaleDateString("pt-BR")}`,
			),
		);
		header.append(titleBlock, makeElement("span", "record-status", contract.status));
		card.append(header);

		if (contract.description) {
			card.append(makeElement("p", "record-description", contract.description));
		}

		const taskList = makeElement("ol", "task-list");
		contract.tasks.forEach((task) => {
			const item = makeElement("li", "", `${task.title} — ${task.status}`);
			taskList.append(item);
		});
		card.append(taskList);
		container.append(card);
	});
}

async function loadTasks() {
	const container = document.querySelector("#tasks-list");
	container.replaceChildren(makeElement("p", "empty-state", "Carregando tarefas..."));
	try {
		const result = await requestJson("/api/tasks");
		renderTasks(result.contracts);
	} catch (error) {
		container.replaceChildren(makeElement("p", "empty-state", error.message));
		if (error.status === 401) {
			currentUser = null;
			updateAccountControls();
			activePage("access");
			pageTitle("access");
		}
	}
}

function renderAdminContracts(contracts) {
	const container = document.querySelector("#admin-contracts-list");
	container.replaceChildren();
	if (contracts.length === 0) {
		container.append(
			makeElement("p", "empty-state", "Ainda não há solicitações de clientes."),
		);
		return;
	}

	contracts.forEach((contract) => {
		const card = makeElement("article", "record-card admin-request-card");
		const header = makeElement("div", "record-heading");
		const titleBlock = document.createElement("div");
		titleBlock.append(makeElement("h2", "", contract.service_title));
		titleBlock.append(
			makeElement("span", "record-date", `Solicitação #${contract.id}`),
		);
		header.append(titleBlock, makeElement("span", "record-status", contract.status));
		card.append(header);

		const createdAt = new Date(contract.created_at);
		card.append(
			makeElement(
				"p",
				"record-date",
				`Cliente: ${contract.customer_email} · ${createdAt.toLocaleString("pt-BR")}`,
			),
		);
		card.append(
			makeElement(
				"p",
				"record-description",
				contract.description || "O cliente não deixou detalhes adicionais.",
			),
		);

		const form = makeElement("form", "admin-status-form");
		form.dataset.adminStatusForm = "";
		const label = makeElement("label", "", "Status da solicitação");
		const select = document.createElement("select");
		select.id = `admin-contract-status-${contract.id}`;
		select.name = "status";
		select.setAttribute("aria-label", `Status da solicitação ${contract.id}`);
		label.htmlFor = select.id;
		contractStatuses.forEach((status) => {
			const option = makeElement("option", "", status);
			option.value = status;
			option.selected = status === contract.status;
			select.append(option);
		});
		const button = makeElement("button", "button primary", "Atualizar status");
		button.type = "submit";
		const message = makeElement("p", "form-message");
		message.setAttribute("role", "status");
		form.append(label, select, button, message);
		form.dataset.contractId = String(contract.id);
		card.append(form);
		container.append(card);
	});
}

async function loadAdminContracts() {
	const container = document.querySelector("#admin-contracts-list");
	container.replaceChildren(makeElement("p", "empty-state", "Carregando solicitações..."));
	try {
		const result = await requestJson("/api/admin/contracts");
		renderAdminContracts(result.contracts);
	} catch (error) {
		container.replaceChildren(makeElement("p", "empty-state", error.message));
		if (error.status === 401 || error.status === 403) {
			await navigate("/", true);
			setGlobalStatus("Esta área é restrita ao responsável pelo projeto.");
		}
	}
}

document.addEventListener("submit", async (event) => {
	const adminStatusForm = event.target.closest("[data-admin-status-form]");
	if (adminStatusForm) {
		event.preventDefault();
		const button = adminStatusForm.querySelector("button[type=submit]");
		const message = adminStatusForm.querySelector(".form-message");
		button.disabled = true;
		message.textContent = "";
		try {
			await requestJson("/api/admin/contracts/status", {
				method: "POST",
				body: JSON.stringify({
					contract_id: Number(adminStatusForm.dataset.contractId),
					status: adminStatusForm.elements.status.value,
				}),
			});
			await loadAdminContracts();
			setGlobalStatus("Status da solicitação atualizado.");
		} catch (error) {
			message.textContent = error.message;
		} finally {
			button.disabled = false;
		}
		return;
	}

	const serviceForm = event.target.closest("[data-service-form]");
	if (serviceForm) {
		event.preventDefault();
		const message = serviceForm.querySelector(".service-message");
		const button = serviceForm.querySelector("button[type=submit]");
		button.disabled = true;
		message.textContent = "";
		try {
			const result = await requestJson("/api/contracts", {
				method: "POST",
				body: JSON.stringify({
					service_id: serviceForm.dataset.serviceId,
					description: serviceForm.elements.description.value,
				}),
			});
			await navigate("/tasks");
			setGlobalStatus(
				result.email_status === "sent"
					? "Solicitação registrada e e-mail enviado. Você pode acompanhar o projeto nesta página."
					: "Solicitação registrada. O e-mail está na fila de envio e será tentado novamente automaticamente.",
			);
		} catch (error) {
			message.textContent = error.message;
			if (error.status === 401) {
				pendingPath = window.location.pathname;
				currentUser = null;
				updateAccountControls();
				await navigate("/access");
			}
		} finally {
			button.disabled = false;
		}
		return;
	}

	const authForm = event.target.closest("[data-auth]");
	if (!authForm) {
		return;
	}
	event.preventDefault();
	const message = authForm.querySelector(".form-message");
	const submitButton = authForm.querySelector("button[type=submit]");
	const formData = new FormData(authForm);
	const email = String(formData.get("email") || "").trim();
	const password = String(formData.get("password") || "");
	const isRegistration = authForm.dataset.auth === "register";
	message.textContent = "";

	if (isRegistration && password !== formData.get("confirm-password")) {
		message.textContent = "As senhas não coincidem.";
		return;
	}

	submitButton.disabled = true;
	try {
		const result = await requestJson(
			isRegistration ? "/api/register" : "/api/login",
			{
				method: "POST",
				body: JSON.stringify({ email, password }),
			},
		);
		currentUser = result.user;
		updateAccountControls();
		await navigate(
			result.user.role === "owner" ? "/admin" : pendingPath || "/",
		);
	} catch (error) {
		message.textContent = error.message;
	} finally {
		submitButton.disabled = false;
	}
});

logoutButton.addEventListener("click", async () => {
	logoutButton.disabled = true;
	try {
		await requestJson("/api/logout", { method: "POST", body: "{}" });
		currentUser = null;
		updateAccountControls();
		setGlobalStatus("Você saiu da sua conta.");
		await navigate("/");
	} catch (error) {
		setGlobalStatus(error.message);
	} finally {
		logoutButton.disabled = false;
	}
});

document.querySelector("#year").textContent = String(new Date().getFullYear());

async function startApplication() {
	let sessionError = "";
	try {
		await refreshSession();
	} catch (error) {
		sessionError = error.message;
	}
	await renderRoute();
	if (sessionError) {
		setGlobalStatus(sessionError);
	}
}

startApplication();
