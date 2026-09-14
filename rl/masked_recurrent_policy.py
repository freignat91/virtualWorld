"""Politique recurrente avec masquage situationnel des actions impossibles."""

from __future__ import annotations

from typing import Any

import torch as th
from stable_baselines3.common.distributions import Distribution

from sb3_contrib.common.recurrent.type_aliases import RNNStates
from sb3_contrib.ppo_recurrent.policies import MlpLstmPolicy

from rl.rl_control import (
    DESTROYER_V5_OBSERVATION_VERSION,
    DESTROYER_V5_TORPEDO_START,
    DESTROYER_V6_OBSERVATION_VERSION,
    MOBILITY_DIRECTIONAL_TORPEDO_SLOT_DIM,
    MOBILITY_TORPEDO_SLOTS,
    SUBMARINE_V3_OBSERVATION_VERSION,
    SUBMARINE_V3_TORPEDO_START,
    SUBMARINE_V4_OBSERVATION_VERSION,
    control_spec,
)


MASKED_CONTROL_VERSIONS = {
    SUBMARINE_V3_OBSERVATION_VERSION,
    SUBMARINE_V4_OBSERVATION_VERSION,
    DESTROYER_V5_OBSERVATION_VERSION,
    DESTROYER_V6_OBSERVATION_VERSION,
}


def situation_action_masks(
        observations: th.Tensor, control_version: str, *,
        mobility_curriculum: bool = False) -> th.Tensor:
    """Construit le masque aplati des categories depuis l'etat public observe."""
    if control_version not in MASKED_CONTROL_VERSIONS:
        raise ValueError(f"masquage indisponible pour {control_version}")
    _, observation_dim, action_nvecs = control_spec(
        "submarine" if control_version in {
            SUBMARINE_V3_OBSERVATION_VERSION,
            SUBMARINE_V4_OBSERVATION_VERSION,
        } else "destroyer",
        control_version,
    )
    flat = observations.reshape(-1, observations.shape[-1])
    if flat.shape[1] != observation_dim:
        raise ValueError(
            f"observation incompatible avec {control_version}: {flat.shape[1]}")
    masks = th.ones(
        (flat.shape[0], int(action_nvecs.sum())), dtype=th.bool, device=flat.device)

    if control_version in {
            SUBMARINE_V3_OBSERVATION_VERSION,
            SUBMARINE_V4_OBSERVATION_VERSION}:
        torpedo_ready = flat[:, 10] > 0.5
        masks[:, 16] = (flat[:, 7] > 0.0) & torpedo_ready
        masks[:, 17] = (flat[:, 8] > 0.0) & torpedo_ready
        masks[:, 19] = (flat[:, 9] > 0.0) & (flat[:, 11] > 0.5)
        torpedo_start = SUBMARINE_V3_TORPEDO_START
        lure_action_index = 19
    else:
        torpedo_ready = flat[:, 11] > 0.5
        masks[:, 11] = (flat[:, 6] > 0.0) & torpedo_ready
        masks[:, 12] = (flat[:, 7] > 0.0) & torpedo_ready
        masks[:, 13] = (flat[:, 8] > 0.0) & (flat[:, 12] > 0.5)
        masks[:, 14] = (flat[:, 9] > 0.0) & (flat[:, 13] > 0.5)
        masks[:, 16] = (flat[:, 10] > 0.0) & (flat[:, 14] > 0.5)
        masks[:, 18] = flat[:, 15] > 0.5
        torpedo_start = DESTROYER_V5_TORPEDO_START
        lure_action_index = 16
    torpedo_end = (
        torpedo_start
        + MOBILITY_TORPEDO_SLOTS * MOBILITY_DIRECTIONAL_TORPEDO_SLOT_DIM)
    visible_torpedo = th.any(
        flat[:, torpedo_start:torpedo_end:MOBILITY_DIRECTIONAL_TORPEDO_SLOT_DIM] > 0.5,
        dim=1,
    )
    masks[:, lure_action_index] &= visible_torpedo
    if mobility_curriculum:
        if control_version in {
                SUBMARINE_V3_OBSERVATION_VERSION,
                SUBMARINE_V4_OBSERVATION_VERSION}:
            masks[:, [16, 17, 19]] = False
        else:
            masks[:, [11, 12, 13, 14, 16, 18]] = False
    return masks


class SituationMaskedMlpLstmPolicy(MlpLstmPolicy):
    """Applique le masque aux logits sans modifier la recurrence PPO."""

    def __init__(self, *args: Any, control_version: str, **kwargs: Any) -> None:
        if control_version not in MASKED_CONTROL_VERSIONS:
            raise ValueError(f"version de controle non masquable: {control_version}")
        self.control_version = control_version
        self.mobility_curriculum = False
        self._situation_masks: th.Tensor | None = None
        super().__init__(*args, **kwargs)

    def _with_observation_masks(self, observations: th.Tensor) -> th.Tensor | None:
        previous = self._situation_masks
        self._situation_masks = situation_action_masks(
            observations, self.control_version,
            mobility_curriculum=self.mobility_curriculum)
        return previous

    def _get_action_dist_from_latent(self, latent_pi: th.Tensor) -> Distribution:
        action_logits = self.action_net(latent_pi)
        if self._situation_masks is not None:
            masks = self._situation_masks.reshape(action_logits.shape)
            action_logits = th.where(
                masks, action_logits, th.full_like(action_logits, -1e8))
        return self.action_dist.proba_distribution(action_logits=action_logits)

    def forward(
        self,
        obs: th.Tensor,
        lstm_states: RNNStates,
        episode_starts: th.Tensor,
        deterministic: bool = False,
    ) -> tuple[th.Tensor, th.Tensor, th.Tensor, RNNStates]:
        previous = self._with_observation_masks(obs)
        try:
            return super().forward(obs, lstm_states, episode_starts, deterministic)
        finally:
            self._situation_masks = previous

    def get_distribution(
        self,
        obs: th.Tensor,
        lstm_states: tuple[th.Tensor, th.Tensor],
        episode_starts: th.Tensor,
    ) -> tuple[Distribution, tuple[th.Tensor, ...]]:
        previous = self._with_observation_masks(obs)
        try:
            return super().get_distribution(obs, lstm_states, episode_starts)
        finally:
            self._situation_masks = previous

    def evaluate_actions(
        self,
        obs: th.Tensor,
        actions: th.Tensor,
        lstm_states: RNNStates,
        episode_starts: th.Tensor,
    ) -> tuple[th.Tensor, th.Tensor, th.Tensor]:
        previous = self._with_observation_masks(obs)
        try:
            return super().evaluate_actions(obs, actions, lstm_states, episode_starts)
        finally:
            self._situation_masks = previous
