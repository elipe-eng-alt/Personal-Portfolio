# Portal e portfólio do Felipe

## Iniciar no Windows

1. Instale o Python 3.10 ou superior, se ainda não estiver instalado.
2. Execute `start.bat`.
3. Abra `http://127.0.0.1:8000` no navegador. Mantenha a janela do servidor aberta enquanto usar o site.
4. Para encerrar, pressione `Ctrl+C` na janela do servidor.

Também é possível iniciar manualmente no terminal, dentro desta pasta:

```powershell
py -3 server.py
```

O servidor usa apenas a biblioteca padrão do Python. Os cadastros, sessões, solicitações de contratação e tarefas ficam no banco SQLite `data/portfolio.sqlite3`, criado automaticamente na primeira inicialização. Esse arquivo não deve ser publicado nem enviado ao Git.

## Notificações de novas solicitações por e-mail

O formulário do catálogo registra o pedido e envia o texto escrito pelo cliente, o e-mail dele e o serviço solicitado para `felipegabrieloliveira1000@gmail.com`.

1. Ative a verificação em duas etapas da sua Conta Google.
2. Crie uma **senha de app** para o Gmail. Não use nem compartilhe a senha normal da conta.
3. Na pasta do projeto, execute `Copy-Item .env.example .env` no PowerShell e substitua `COLE_SUA_SENHA_DE_APP_AQUI` no arquivo `.env` pela senha de app do Gmail, sem espaços.
4. Execute ou reinicie `start.bat` para carregar as configurações. Nunca cole a senha aqui no chat, no código-fonte ou em um repositório público.

O envio usa SMTP autenticado com STARTTLS e validação do certificado. O endereço de destino é fixado no servidor; o cliente não pode escolher o destinatário. Se o provedor estiver indisponível ou a senha ainda não estiver configurada, a solicitação continua salva e o servidor mantém a notificação em uma fila SQLite, tentando novamente automaticamente. A página informa quando o envio está pendente. Os detalhes das solicitações ficam no banco local.

A API usada pelo formulário é `POST /api/contracts`, com a sessão de cliente autenticada e um JSON como `{"service_id":"custom-project","description":"Preciso de um site para minha loja."}`. O servidor busca o e-mail do cliente da sessão e envia o texto em e-mail simples, com o seu endereço como único destinatário e o e-mail do cliente configurado como endereço para resposta.

As rotas de escrita exigem uma origem válida. Um cliente autenticado pode enviar até cinco solicitações por hora. Se publicar o site, configure `APP_ORIGIN` com a origem HTTPS exata do domínio e cadastre as variáveis SMTP nos segredos do serviço de hospedagem em vez de salvar o `.env` no servidor público.

## Preparar HTTPS com Caddy

O arquivo `Caddyfile` prepara o proxy HTTPS automático do Caddy para um servidor público na mesma máquina do backend:

1. Registre um domínio e crie um registro DNS `A` apontando para o endereço IPv4 público do servidor. Crie um `AAAA` somente se o servidor também aceitar conexões IPv6.
2. Instale o Caddy no servidor e substitua `felipe-portfolio.example.com` no `Caddyfile` pelo domínio real.
3. Permita conexões de entrada nas portas TCP `80` e `443` no firewall do servidor e do provedor.
4. Configure `APP_ORIGIN=https://felipe-portifolio.com` no ambiente do backend, exatamente igual ao domínio do `Caddyfile`. Em produção, `SMTP_USER` e `SMTP_PASSWORD` também devem ficar em variáveis protegidas no servidor; não copie credenciais para este repositório.
5. Mantenha o backend escutando apenas em `127.0.0.1:8000`. Inicie o Caddy com o `Caddyfile` e configure ambos, Caddy e backend, para iniciar como serviços persistentes do servidor.
6. Quando o DNS estiver propagado e as portas acessíveis, o Caddy solicita e renova automaticamente o certificado HTTPS. Acesse o site por `https://felipe-portifolio.com`.

O certificado público não pode ser emitido para `localhost`, nem ativado de verdade até que um domínio real aponte para um servidor publicamente acessível. O HSTS do `Caddyfile` só deve ser usado no domínio HTTPS final.

## Páginas do portal

- **Dashboard:** exibe solicitações mensais de contratação realmente registradas no banco. Não processa pagamentos nem confirma vendas pagas.
- **Serviços:** catálogo com formulário para enviar uma solicitação.
- **Projetos:** exige uma conta de cliente. O cliente pode entrar ou criar cadastro antes de continuar.
- **Tarefas:** requer login e mostra apenas as solicitações e etapas do cliente conectado.
- **Cadastro:** exige e-mail válido e senha de 10 a 128 caracteres. A senha é armazenada com hash PBKDF2-HMAC-SHA256; o texto original não é guardado.

Este servidor é para desenvolvimento local e escuta apenas em `127.0.0.1`. Para publicar o site na internet, será necessário hospedar a aplicação atrás de HTTPS e configurar os controles de produção apropriados; não exponha o servidor de desenvolvimento diretamente.

## Testes

```powershell
py -3 -m unittest -v
```
