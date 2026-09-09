import logging
import os
import asyncio
from contextlib import asynccontextmanager
from pathlib import Path
from time import perf_counter
from typing import Annotated
from uuid import UUID, uuid4

import psycopg
from fastapi import Depends, FastAPI, Header, Query, Request, Response
from fastapi.responses import JSONResponse, HTMLResponse, RedirectResponse
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials

from banking_api.db import connect
from banking_api.models import Account, AccountCreate, History, Transfer, TransferCreate
from banking_api.service import BankingError, BankingService
from banking_api.sandbox import authenticate, start_session, cleanup, BodyLimitMiddleware

logger = logging.getLogger('uvicorn.error')


def create_app(database_url=None, public_demo=None):
    public_demo = public_demo if public_demo is not None else os.environ.get('BANKING_PUBLIC_DEMO') == '1'

    def cleanup_once():
        with connect(database_url) as conn:
            cleanup(conn)

    @asynccontextmanager
    async def lifespan(app):
        async def sweep():
            while True:
                try:
                    await asyncio.to_thread(cleanup_once)
                except psycopg.Error:
                    logger.warning('Demo cleanup deferred due to database error')
                await asyncio.sleep(60)
        task = asyncio.create_task(sweep()) if public_demo else None
        try:
            yield
        finally:
            if task:
                task.cancel()
                try:
                    await task
                except asyncio.CancelledError:
                    pass

    app = FastAPI(
        lifespan=lifespan,
        title='Neobank Transaction API', version='1.0.0',
        description='Portfolio simulation with synthetic funds only. GBP amounts are integer pence. '
                    + ('First create a session at POST /demo/sessions, then click Authorize and paste its token. Sessions expire after 30 minutes. ' if public_demo else 'Local mode: no authentication. ')
                    + 'No real payments. Use fictional names only.',
    )

    bearer = HTTPBearer(auto_error=False)
    def service(credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer)]):
        with connect(database_url) as conn:
            session_id = authenticate(conn, credentials.credentials if credentials else None) if public_demo else None
            yield BankingService(conn, session_id)

    Service = Annotated[BankingService, Depends(service)]

    if public_demo:
        app.add_middleware(BodyLimitMiddleware)

        @app.post('/demo/sessions', status_code=201)
        def new_session():
            with connect(database_url) as conn:
                return start_session(conn)

    @app.get('/', response_class=HTMLResponse, include_in_schema=False)
    def welcome():
        if not public_demo:
            return RedirectResponse('/docs')
        return Path(__file__).with_name('welcome.html').read_text()

    @app.middleware('http')
    async def request_log(request: Request, call_next):
        request_id = str(uuid4())
        start = perf_counter()
        response = await call_next(request)
        response.headers['X-Request-ID'] = request_id
        response.headers['X-Content-Type-Options'] = 'nosniff'
        response.headers['Referrer-Policy'] = 'no-referrer'
        response.headers['Cache-Control'] = 'no-store'
        route = request.scope.get('route')
        logger.info('request_id=%s method=%s route=%s status=%s duration_ms=%.2f',
                    request_id, request.method, getattr(route, 'path', 'unmatched'),
                    response.status_code, (perf_counter() - start) * 1000)
        return response

    @app.exception_handler(BankingError)
    async def banking_error(request, exc):
        return JSONResponse(status_code=exc.status, content={'error': {'code': exc.code, 'message': exc.message}})

    @app.exception_handler(psycopg.OperationalError)
    async def unavailable(request, exc):
        return JSONResponse(status_code=503, headers={'Retry-After': '1'},
                            content={'error': {'code': 'database_unavailable', 'message': 'Database temporarily unavailable; retry with the same idempotency key'}})

    @app.get('/health')
    def health():
        with connect(database_url) as conn:
            conn.execute('SELECT 1 FROM banking.accounts LIMIT 1')
        return {'status': 'ok'}

    @app.post('/accounts', response_model=Account, status_code=201)
    def create_account(body: AccountCreate, svc: Service):
        return svc.create_account(body)

    @app.get('/accounts/{account_id}', response_model=Account)
    def get_account(account_id: UUID, svc: Service):
        return svc.account(account_id)

    @app.post('/transfers', response_model=Transfer, status_code=201,
              responses={200: {'description': 'Previously committed transfer replayed'},
                         409: {'description': 'Insufficient funds or conflicting key'}})
    def transfer(body: TransferCreate, response: Response, svc: Service,
                 idempotency_key: Annotated[str, Header(min_length=1, max_length=128, pattern=r'^[A-Za-z0-9._:-]+$')]):
        result, replayed = svc.transfer(body, idempotency_key)
        response.status_code = 200 if replayed else 201
        response.headers['Idempotency-Replayed'] = str(replayed).lower()
        return result

    @app.get('/accounts/{account_id}/transactions', response_model=History)
    def history(account_id: UUID, svc: Service,
                limit: Annotated[int, Query(ge=1, le=100)] = 20,
                offset: Annotated[int, Query(ge=0, le=10000)] = 0):
        return svc.history(account_id, limit, offset)

    return app


app = create_app()
