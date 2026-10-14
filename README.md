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
