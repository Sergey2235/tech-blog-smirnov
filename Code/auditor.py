"""Unified auditor for GitLab and GitHub."""
import logging
from gitlab_client import GitLabClient
from github_client import GitHubClient
from llm_client import LLMClient

logger = logging.getLogger(__name__)


class CodeAuditor:
    def __init__(self, gitlab_client: GitLabClient = None, github_client: GitHubClient = None, llm_client: LLMClient = None):
        self.gitlab = gitlab_client
        self.github = github_client
        self.llm = llm_client

    # ==================== GitLab ====================
    
    async def audit_gitlab_mr(self, project, mr_iid: int, audit_type: str = "full", create_mr: bool = True) -> str:
        """Audit GitLab Merge Request."""
        logger.info(f"GitLab MR audit: #{mr_iid} ({audit_type})")
        
        changes = self.gitlab.get_merge_request_changes(project, mr_iid)
        files_to_check = self._collect_files(changes)
        
        if not files_to_check:
            return "No files to check"
        
        results = await self.llm.analyze_batch(files_to_check, audit_type)
        report = self._generate_report(results, audit_type)
        
        branch_name = self.gitlab.config.branch
        self.gitlab.create_branch(project, branch_name, ref=changes["changes"][0]["base_commit"]["id"])
        
        self.gitlab.create_commit(
            project, branch_name, self.gitlab.config.commit_message,
            {f"mr-{mr_iid}-audit-{audit_type}": report}
        )
        
        comment = f"## Code Audit ({audit_type.upper()})\n\n{report}\n\n_Auto-generated_"
        self.gitlab.add_merge_request_note(project, mr_iid, comment)
        
        if create_mr:
            self.gitlab.create_merge_request(
                project, f"Code Audit MR #{mr_iid} [{audit_type.upper()}]",
                report, branch_name
            )
        
        return "GitLab MR audit completed"

    async def audit_gitlab_commit(self, project, commit_sha: str, audit_type: str = "full") -> str:
        """Audit GitLab commit."""
        logger.info(f"GitLab commit audit: {commit_sha[:8]} ({audit_type})")
        
        diffs = self.gitlab.get_commit_diff(project, commit_sha)
        files_to_check = {}
        
        for diff in diffs:
            file_path = diff.get("new_path", diff.get("old_path", ""))
            content = diff.get("diff", "")
            if content:
                files_to_check[file_path] = content[:5000]
        
        if not files_to_check:
            return "No files to check"
        
        results = await self.llm.analyze_batch(files_to_check, audit_type)
        report = self._generate_report(results, audit_type)
        
        branch_name = self.gitlab.config.branch
        self.gitlab.create_branch(project, branch_name, ref=commit_sha)
        
        self.gitlab.create_commit(
            project, branch_name, self.gitlab.config.commit_message,
            {f"commit-{commit_sha[:8]}-audit-{audit_type}": report}
        )
        
        return "GitLab commit audit completed"

    # ==================== GitHub ====================
    
    async def audit_github_pr(self, repo, pr_number: int, audit_type: str = "full", create_pr: bool = True) -> str:
        """Audit GitHub Pull Request."""
        logger.info(f"GitHub PR audit: #{pr_number} ({audit_type})")
        
        files = self.github.get_pull_request_files(repo, pr_number)
        files_to_check = {}
        
        for f in files:
            if f.filename.endswith((".png", ".jpg", ".pdf", ".exe", ".zip")):
                continue
            if "/node_modules/" in f.filename or "/vendor/" in f.filename:
                continue
            if f.patch:
                files_to_check[f.filename] = f.patch[:5000]
        
        if not files_to_check:
            return "No files to check"
        
        results = await self.llm.analyze_batch(files_to_check, audit_type)
        report = self._generate_report(results, audit_type)
        
        # Create branch with report
        branch_name = "code-audit"
        pr = repo.get_pull(pr_number)
        base_sha = pr.head.sha
        
        self.github.create_branch(repo, branch_name, base_sha)
        
        self.github.create_file(
            repo, 
            f"audit/pr-{pr_number}-audit-{audit_type}.md",
            report,
            "chore: code quality audit via LLM",
            branch_name
        )
        
        # Comment on PR
        comment = f"## Code Audit ({audit_type.upper()})\n\n{report}\n\n_Auto-generated_"
        self.github.add_pull_request_comment(repo, pr_number, comment)
        
        if create_pr:
            self.github.create_pull_request(
                repo,
                f"Code Audit PR #{pr_number} [{audit_type.upper()}]",
                report,
                branch_name,
                pr.base.ref
            )
        
        return "GitHub PR audit completed"

    async def audit_github_commit(self, repo, sha: str, audit_type: str = "full") -> str:
        """Audit GitHub commit."""
        logger.info(f"GitHub commit audit: {sha[:8]} ({audit_type})")
        
        diffs = self.github.get_commit_diff(repo, sha)
        files_to_check = {}
        
        for diff in diffs:
            file_path = diff.get("filename", "")
            if file_path.endswith((".png", ".jpg", ".pdf", ".exe", ".zip")):
                continue
            patch = diff.get("patch", "")
            if patch:
                files_to_check[file_path] = patch[:5000]
        
        if not files_to_check:
            return "No files to check"
        
        results = await self.llm.analyze_batch(files_to_check, audit_type)
        report = self._generate_report(results, audit_type)
        
        branch_name = "code-audit"
        self.github.create_branch(repo, branch_name, sha)
        
        self.github.create_file(
            repo,
            f"audit/commit-{sha[:8]}-audit-{audit_type}.md",
            report,
            "chore: code quality audit via LLM",
            branch_name
        )
        
        return "GitHub commit audit completed"

    # ==================== Helpers ====================
    
    def _collect_files(self, changes: dict) -> dict:
        """Collect files from GitLab changes."""
        files = {}
        for change in changes.get("changes", []):
            file_path = change["new_path"]
            if any(file_path.endswith(ext) for ext in [".png", ".jpg", ".pdf", ".exe", ".zip"]):
                continue
            if "/node_modules/" in file_path or "/vendor/" in file_path:
                continue
            diff = change.get("diff", "")
            if diff:
                files[file_path] = diff[:5000]
        return files

    def _generate_report(self, results: dict[str, str], audit_type: str) -> str:
        """Generate audit report."""
        type_names = {
            "full": "Full Check",
            "security": "Security",
            "performance": "Performance",
            "style": "Code Style"
        }
        
        lines = [f"# Code Audit Report ({type_names.get(audit_type, audit_type)})\n"]
        
        has_issues = False
        for file_path, analysis in results.items():
            lines.append(f"\n## {file_path}\n")
            lines.append(f"```\n{analysis}\n```\n")
            if "OK" not in analysis:
                has_issues = True
        
        if not has_issues:
            lines.append("\n## Summary\nAll files passed inspection.\n")
        else:
            lines.append("\n## Summary\nIssues found that need attention.\n")
        
        return "".join(lines)
