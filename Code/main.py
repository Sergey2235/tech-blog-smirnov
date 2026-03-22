"""Точка входа в приложение."""
import argparse
import asyncio
import logging
import sys

from config import get_config
from gitlab_client import GitLabClient
from llm_client import LLMClient
from auditor import CodeAuditor

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


async def main():
    parser = argparse.ArgumentParser(
        description="LLM Code Auditor - автоматизация проверки качества кода"
    )
    parser.add_argument(
        "url",
        help="URL GitLab (репозиторий, MR или коммит)"
    )
    parser.add_argument(
        "--type",
        choices=["mr", "commit", "repo"],
        help="Тип ресурса (определяется автоматически, если не указан)"
    )
    parser.add_argument(
        "--mr-id",
        type=int,
        help="ID Merge Request (если URL указывает на репозиторий)"
    )
    parser.add_argument(
        "--commit-sha",
        help="SHA коммита (если URL указывает на репозиторий)"
    )
    parser.add_argument(
        "--no-mr",
        action="store_true",
        help="Не создавать Merge Request с отчётом"
    )
    
    args = parser.parse_args()
    
    config = get_config()
    
    if not config.llm.api_key:
        logger.error("LLM API key не настроен. Проверьте .env файл")
        sys.exit(1)
    
    if not config.gitlab.token:
        logger.error("GitLab token не настроен. Проверьте .env файл")
        sys.exit(1)
    
    # Инициализация клиентов
    gitlab_client = GitLabClient(config.gitlab)
    llm_client = LLMClient(config.llm)
    auditor = CodeAuditor(gitlab_client, llm_client)
    
    # Парсинг URL
    try:
        namespace, project_name, resource_type, resource_id = gitlab_client.parse_gitlab_url(args.url)
    except ValueError as e:
        logger.error(e)
        sys.exit(1)
    
    project = gitlab_client.get_project(namespace, project_name)
    logger.info(f"Проект: {project.name}")
    
    # Определение типа ресурса
    if args.type == "mr" or resource_type == "mr":
        mr_id = args.mr_id or resource_id
        if not mr_id:
            logger.error("Укажите ID Merge Request")
            sys.exit(1)
        result = await auditor.audit_merge_request(project, int(mr_id), create_mr=not args.no_mr)
        
    elif args.type == "commit" or resource_type == "commit":
        commit_sha = args.commit_sha or resource_id
        if not commit_sha:
            logger.error("Укажите SHA коммита")
            sys.exit(1)
        result = await auditor.audit_commit(project, commit_sha)
        
    elif args.type == "repo" or resource_type is None:
        # Аудит последних изменений в репозитории
        logger.info("Аудит репозитория не реализован. Используйте MR или commit")
        sys.exit(1)
    
    logger.info(f"Результат: {result}")


if __name__ == "__main__":
    asyncio.run(main())
