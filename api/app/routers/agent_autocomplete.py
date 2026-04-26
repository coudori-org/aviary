from fastapi import APIRouter, Depends, HTTPException

from app.auth.dependencies import get_session_data
from app.auth.session_store import SessionData
from app.schemas.agent_autocomplete import (
    AgentAutocompleteRequest,
    AgentAutocompleteResponse,
)
from app.services import agent_autocomplete_service

router = APIRouter()


@router.post("", response_model=AgentAutocompleteResponse)
async def autocomplete(
    body: AgentAutocompleteRequest,
    session: SessionData = Depends(get_session_data),
):
    try:
        return await agent_autocomplete_service.run(
            body, session.id_token or "", session.user_external_id,
        )
    except agent_autocomplete_service.AutocompleteError as e:
        raise HTTPException(status_code=502, detail=str(e))
