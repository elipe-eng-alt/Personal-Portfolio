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

O servidor usa apenas a biblioteca padrão do Python. Os cadastros, sessões, solicitações de contratação, tarefas e fila de e-mails ficam no banco SQLite. Localmente, o arquivo padrão é `data/portfolio.sqlite3`; use `DATABASE_PATH` para escolher outro caminho. O banco não deve ser publicado nem enviado ao Git.

## Notificações de novas solicitações por e-mail

O formulário do catálogo registra o pedido e envia o texto escrito pelo cliente, o e-mail dele e o serviço solicitado para `felipegabrieloliveira1000@gmail.com`.

Na hospedagem Render, configure o envio recomendado por HTTPS:

1. Crie uma conta no Resend e gere uma API key.
2. Configure `RESEND_API_KEY` no painel do Render como variável secreta. Não coloque a chave no repositório ou no chat.
3. Para testes, o remetente padrão é `Felipe Portfolio <onboarding@resend.dev>`; para produção, valide um domínio no Resend e defina `EMAIL_FROM` com um remetente desse domínio.
4. Salve as variáveis e faça o redeploy do serviço.

O Render pode bloquear o SMTP de saída nas portas comuns de e-mail. Por isso, o Resend envia por HTTPS. SMTP autenticado com STARTTLS permanece disponível para provedores/hospedagens que permitem conexões SMTP, usando `SMTP_HOST`, `SMTP_PORT`, `SMTP_USER` e `SMTP_PASSWORD`.

O endereço de destino é fixado no servidor em `felipegabrieloliveira1000@gmail.com`; o cliente não pode escolher o destinatário. Se o provedor estiver indisponível ou não estiver configurado, a solicitação continua salva e a notificação fica na fila SQLite para novas tentativas. `/api/health` informa se há provedor configurado e quantos e-mails estão pendentes, sem revelar credenciais.

A API usada pelo formulário é `POST /api/contracts`, com a sessão de cliente autenticada e um JSON como `{"service_id":"custom-project","description":"Preciso de um site para minha loja."}`. O servidor busca o e-mail do cliente da sessão e envia o texto em e-mail simples, com o seu endereço como único destinatário e o e-mail do cliente configurado como endereço para resposta.

As rotas de escrita exigem uma origem válida. Um cliente autenticado pode enviar até cinco solicitações por hora. Se publicar o site, configure `APP_ORIGIN` com a origem HTTPS exata do domínio e cadastre as credenciais do Resend ou SMTP nos segredos do serviço de hospedagem em vez de salvar o `.env` no servidor público.

### Configurar o serviço no Render

No painel do Render, abra o serviço `personal-portfolio-0lg6`:

1. Em **Environment**, configure `APP_ORIGIN=https://personal-portfolio-0lg6.onrender.com`, `DATABASE_PATH=/var/data/portfolio.sqlite3` e `RESEND_API_KEY`. Opcionalmente configure `EMAIL_FROM` após validar o domínio no Resend.
2. Em **Disks**, adicione um disco persistente montado em `/var/data`. O Render não importa `.env.example`; defina as variáveis no painel.
3. Em **Settings**, configure o Health Check Path como `/health`. O servidor usa automaticamente a porta fornecida pelo Render e escuta em `0.0.0.0`.
4. Salve e faça o redeploy. Consulte `/api/health`: `database` deve ser `ok`, `email_provider` deve ser `configured` e `pending_emails` deve diminuir depois do envio.

**Persistência:** o SQLite fica no disco ligado ao serviço. Sem um disco persistente, os arquivos do sistema de arquivos do serviço podem desaparecer em reinicializações ou novos deploys; com SQLite e disco, mantenha uma única instância da aplicação. Discos persistentes podem exigir um plano pago no Render; confira o preço no painel antes de ativar. Se seu plano não permitir disco, use um banco PostgreSQL gerenciado e migre o backend antes de publicar.

Cadastros e solicitações que não foram gravados em um banco persistente antigo não podem ser recuperados por este ajuste. Depois de conectar o disco, os novos cadastros e pedidos serão gravados em `/var/data/portfolio.sqlite3` e sobreviverão aos deploys.

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
