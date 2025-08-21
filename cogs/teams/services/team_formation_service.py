import logging
from typing import Dict, List, Tuple, Optional
from collections import defaultdict
import numpy as np
from discord import Guild, utils
from ..utils.team_utils import fetch_member_safely, provision_roles_for_new_members, provision_team_resources, build_team_from_data
from ..models.team import Team, TeamConfig, TeamMember, TeamNotFoundError
from .scoring_engine import TeamScoringEngine
from config import MIN_CATEGORY_SCORE_THRESHOLD, MIN_TIMEZONE_SCORE_THRESHOLD

logger = logging.getLogger(__name__)

class TeamFormationService:
    """
    Orchestrates the new hierarchical team formation algorithm and other
    team assignment-related tasks. This refactored version leverages
    centralized methods from other services to reduce redundancy.
    """

    def __init__(self, scorer: TeamScoringEngine, db_manager, team_manager_instance):
        self.scorer = scorer
        self.db = db_manager
        self.team_manager = team_manager_instance
        self.config = TeamConfig()

    async def form_teams_hierarchical(self, unassigned_leaders: List[Dict], unassigned_members: List[Dict]) -> List[Team]:
        """Forms new teams using a multi-phase hierarchical clustering algorithm."""
        logger.info("="*50 + "\n🚀 STARTING HIERARCHICAL TEAM FORMATION\n" + "="*50)

        all_members = []
        for profile_dict in unassigned_leaders + unassigned_members:
            # Extract the user_id if it's in the profile_dict, or use a key from the dict
            if 'user_id' in profile_dict:
                user_id = profile_dict['user_id']
            else:
                # If user_id is not in the dict, we need to pass it separately
                # This suggests the data structure might need to be adjusted
                logger.error(f"Missing user_id in profile data: {profile_dict}")
                continue

            # Create TeamMember with user_id as first positional argument
            team_member = TeamMember(
                user_id=user_id,
                username=profile_dict.get('username', ''),
                display_name=profile_dict.get('display_name', ''),
                role_title=profile_dict.get('role_title', ''),
                profile_data=profile_dict.get('profile_data', {})
            )
            all_members.append(team_member)

        logger.info(f"🌱 Initializing with {len([m for m in all_members if m.is_leader()])} leaders and {len([m for m in all_members if not m.is_leader()])} members.")

        # Phases 1 & 2: Timezone and Category Clustering
        proposed_teams, category_orphans = self._cluster_by_category(self._cluster_by_timezone(all_members))
        logger.info(f"🎯 Initial Clustering Complete: {len(proposed_teams)} teams created, {len(category_orphans)} members initially unassigned.")

        # Phase 3: Semantic Optimization of Oversized Teams
        final_teams, semantic_orphans = [], []
        for team in proposed_teams:
            if len(team.members) > self.config.max_team_size:
                optimized_team, new_orphans = await self._optimize_oversized_team(team)
                final_teams.append(optimized_team)
                semantic_orphans.extend(new_orphans)
            else:
                final_teams.append(team)
        if semantic_orphans:
            logger.info(f"🧠 Semantic Optimization Complete. {len(semantic_orphans)} members moved to orphan pool.")

        # Phase 4: Reassignment of All Orphans
        all_orphans = category_orphans + semantic_orphans
        if all_orphans:
            final_teams, still_unassigned = self._reassign_orphans(all_orphans, final_teams)
            reassigned_count = len(all_orphans) - len(still_unassigned)
            logger.info(f"🤝 Orphan Reassignment Complete: {reassigned_count} members placed. {len(still_unassigned)} remain unassigned.")
            if still_unassigned:
                logger.warning(f"🚨 Final Unassigned Members: {[m.display_name for m in still_unassigned]}")

        logger.info("="*50 + "\n✅ TEAM FORMATION PROCESS COMPLETE\n" + "="*50)
        return final_teams

    def _cluster_by_timezone(self, all_members: List[TeamMember]) -> Dict[Optional[float], List[TeamMember]]:
        """Phase 1: Groups all members by their UTC timezone offset."""
        logger.info("Phase 1: Clustering members by timezone...")
        timezone_clusters = defaultdict(list)
        for member in all_members:
            tz_string = member.profile_data.get("timezone")
            utc_offset = self.scorer.tz_processor.parse_to_utc_offset(tz_string) if tz_string else None
            timezone_clusters[utc_offset].append(member)
        logger.info(f"-> Found {len(timezone_clusters)} distinct timezone groups.")
        return timezone_clusters

    def _cluster_by_category(self, timezone_clusters: Dict[Optional[float], List[TeamMember]]) -> Tuple[List[Team], List[TeamMember]]:
        """Phase 2: Forms initial teams based on category similarity within timezone groups."""
        logger.info("Phase 2: Clustering by category...")
        formed_teams, all_orphans = [], []

        for tz_offset, members in timezone_clusters.items():
            leaders = [m for m in members if m.is_leader()]
            if not leaders:
                all_orphans.extend(members)
                continue

            non_leaders = [m for m in members if not m.is_leader()]
            leader_cats = {l.user_id: self.scorer.get_member_categories(l.profile_data) for l in leaders}
            team_assignments = defaultdict(list, {l.user_id: [l] for l in leaders})

            for member in non_leaders:
                member_cats = self.scorer.get_member_categories(member.profile_data)
                leader_scores = {
                    leader.user_id: self.scorer._calculate_categorical_score(member_cats, leader_cats[leader.user_id])
                    for leader in leaders
                }

                if not leader_scores: continue
                best_leader_id, best_score = max(leader_scores.items(), key=lambda item: item[1])

                if best_score >= MIN_CATEGORY_SCORE_THRESHOLD:
                    team_assignments[best_leader_id].append(member)
                else:
                    all_orphans.append(member)

            for members_list in team_assignments.values():
                leader_name = members_list[0].display_name
                formed_teams.append(Team(
                    guild_id=0, team_role=f"Team {leader_name}",
                    channel_name=f"{leader_name.lower().replace(' ', '-')}",
                    members={m.user_id: m for m in members_list}
                ))
        return formed_teams, all_orphans

    async def _optimize_oversized_team(self, team: Team) -> Tuple[Team, List[TeamMember]]:
        """Phase 3a: Trims an oversized team using semantic similarity to find the most cohesive members."""
        logger.info(f"Phase 3a: Optimizing oversized team '{team.team_role}' ({len(team.members)} members)...")
        members = list(team.members.values())
        size = len(members)
        scores = np.zeros((size, size))

        for i in range(size):
            for j in range(i + 1, size):
                score = await self.scorer.calculate_semantic_compatibility(members[i].profile_data, members[j].profile_data)
                scores[i, j] = scores[j, i] = score

        avg_scores = {members[i].user_id: np.mean(scores[i]) for i in range(size)}

        leaders = [m for m in members if m.is_leader()]
        non_leaders = sorted([m for m in members if not m.is_leader()], key=lambda m: avg_scores[m.user_id], reverse=True)

        slots_for_members = self.config.max_team_size - len(leaders)
        kept_members = leaders + non_leaders[:slots_for_members]
        orphans = non_leaders[slots_for_members:]

        team.members = {m.user_id: m for m in kept_members}
        return team, orphans

    def _reassign_orphans(self, orphans: List[TeamMember], teams: List[Team]) -> Tuple[List[Team], List[TeamMember]]:
        """Phase 4: Reassigns orphans using a tiered, timezone-first logic."""
        logger.info(f"Phase 4: Reassigning {len(orphans)} orphaned members...")
        unassigned = []

        for orphan in orphans:
            candidate_teams = []
            for team in teams:
                if len(team.members) >= self.config.max_team_size: continue

                team_leaders = [vars(m) for m in team.get_leaders()] # Use vars() to pass dict
                if not team_leaders: continue

                # Use the centralized scoring method
                fit_scores = self.scorer.calculate_member_team_fit(orphan.profile_data, team_leaders)
                candidate_teams.append({'team': team, 'size': len(team.members), **fit_scores})

            if not candidate_teams:
                unassigned.append(orphan)
                continue

            # Tier 1: Find teams that are a good timezone fit
            primary_candidates = [c for c in candidate_teams if c['tz_score'] >= MIN_TIMEZONE_SCORE_THRESHOLD]

            # From the good fits, pick the one with the best category score (and smallest size as tie-breaker)
            if primary_candidates:
                best_team = max(primary_candidates, key=lambda x: (x['cat_score'], -x['size']))['team']
            # Tier 2: If no team is a good timezone fit, pick the "least bad" option (best available TZ score)
            else:
                best_team = max(candidate_teams, key=lambda x: (x['tz_score'], x['cat_score'], -x['size']))['team']

            best_team.members[orphan.user_id] = orphan

        return teams, unassigned

    async def find_best_teams_for_member(self, member_profile: Dict, all_teams: List[Team]) -> List[Dict]:
        """Finds and ranks the best existing teams for a single member to join."""
        profile_data = member_profile.get("profile_data", {})
        recommendations = []

        for team in all_teams:
            if len(team.members) >= self.config.max_team_size: continue

            team_leaders = [vars(m) for m in team.get_leaders()]
            if not team_leaders: continue

            # Use the centralized scoring method, removing duplicated logic
            fit_scores = self.scorer.calculate_member_team_fit(profile_data, team_leaders)
            recommendations.append({
                "team_name": team.team_role,
                "size": len(team.members),
                **fit_scores
            })

        # Sort by timezone score, then category score, then smallest size (as tie-breaker)
        recommendations.sort(key=lambda x: (x["tz_score"], x["cat_score"], -x["size"]), reverse=True)

        return [
            {"team_name": rec["team_name"], "score": f"TZ: {rec['tz_score']:.2f}, Cat: {rec['cat_score']:.2f}"}
            for rec in recommendations
        ]

    async def assign_member_to_team(self, guild: Guild, user_id: str, team_name: str) -> Tuple[bool, str]:
        """Assigns a single unregistered member to an existing team."""
        try:
            # 1. Fetch team object using the team manager for consistency
            team = await self.team_manager.get_team(guild.id, team_name)
        except TeamNotFoundError:
            return False, f"Team '{team_name}' could not be found."

        # 2. Fetch the unregistered member's profile data
        unregistered_doc = await self.db.get_unregistered_document(guild.id)
        member_profile = (unregistered_doc.get("leaders", {}).get(user_id) or
                          unregistered_doc.get("members", {}).get(user_id))

        if not member_profile:
            return False, "Could not find the profile for the unassigned member."

        # 3. Add member and update database
        team.members[user_id] = TeamMember(user_id=user_id, **member_profile)
        await self.db.update_team_members(guild.id, team.team_role, {uid: vars(mem) for uid, mem in team.members.items()})
        await self.db.remove_unregistered_member(guild.id, user_id)

        # 4. Assign Discord role
        discord_member = await fetch_member_safely(guild, user_id)
        team_role = utils.get(guild.roles, name=team.team_role)
        if discord_member and team_role:
            await discord_member.add_roles(team_role, reason=f"Assigned to team {team.team_role}")

        marathon_active = await self.team_manager.team_service.is_marathon_active(guild.id)

        if marathon_active:
            await provision_roles_for_new_members(guild, team.team_role, [team.members[user_id]])
            return True, f"✅ Member assigned to `{team.team_role}`."
        else:
            return True, f"✅ Member assigned to `{team.team_role}` in database only (marathon inactive)."

    async def batch_create_teams(self, guild: Guild, proposed_teams: List[Team]) -> Dict:
        """Creates multiple teams in the database from a proposed formation."""
        created_count, failed_teams = 0, []
        for i, team_obj in enumerate(proposed_teams, 1):
            try:
                new_team_number = await self.db.get_max_team_number(guild.id) + 1
                team_role_name = f"Team {new_team_number}"

                # Use the refactored insert_team method that takes a single dict
                await self.db.insert_team({
                    "guild_id": guild.id,
                    "team_number": new_team_number,
                    "team_role": team_role_name,
                    "channel_name": f"team-{new_team_number}",
                    "members": {uid: vars(member) for uid, member in team_obj.members.items()}
                })

                marathon_active = await self.team_manager.team_service.is_marathon_active(guild.id)
                if marathon_active:
                    raw_team_data = await self.db.get_team_by_name(guild.id, team_role_name)
                    team = build_team_from_data(guild.id, raw_team_data)
                    await provision_team_resources(guild, team)

                for user_id in team_obj.members.keys():
                    await self.db.remove_unregistered_member(guild.id, user_id)
                created_count += 1
            except Exception as e:
                logger.error(f"Failed to create proposed team {i}: {e}", exc_info=True)
                failed_teams.append(f"Proposed Team {i}")

        return {"created": created_count, "failed": failed_teams}
