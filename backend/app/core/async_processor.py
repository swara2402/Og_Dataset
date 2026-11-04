import asyncio
import time
import logging
from typing import List, Optional, Callable, Any, Dict
from dataclasses import dataclass, field
from collections import OrderedDict

logger = logging.getLogger(__name__)

@dataclass
class TaskResult:
    task_id: str
    original_index: int
    success: bool
    revised_content: str = ""
    error: str = ""
    processing_time: float = 0.0

@dataclass
class Batch:
    items: List[Any]
    batch_id: str

@dataclass
class Job:
    job_id: str
    items: List[Any]
    created_time: float = field(default_factory=time.time)
    completed: bool = False
    cancelled: bool = False
    results: List[TaskResult] = field(default_factory=list)
    progress_callback: Optional[Callable[[int, int], None]] = None

class ResultCache:
    """LRU cache for processing results to avoid redundant work."""
    def __init__(self, max_size: int = 1000):
        self.cache: OrderedDict[str, Any] = OrderedDict()
        self.max_size = max_size
    
    def get(self, key: str) -> Optional[Any]:
        if key in self.cache:
            self.cache.move_to_end(key)
            return self.cache[key]
        return None
    
    def put(self, key: str, value: Any) -> None:
        if key in self.cache:
            self.cache.move_to_end(key)
            self.cache[key] = value
            if len(self.cache) > self.max_size:
                self.cache.popitem(last=False)

class AsyncProcessor:
    """
    Asynchronous processor for document humanisation.
    100% reliable: processes EVERY paragraph, no skips, with maximum concurrency.
    """
    def __init__(
        self,
        max_concurrent_tasks: int = 16,  # Process 16 items at once for speed (no skips)
        cache_size: int = 1000
    ):
        self.max_concurrent_tasks = max_concurrent_tasks  # High concurrency = fast processing
        self._jobs: Dict[str, Job] = {}
        self._tasks: set[asyncio.Task] = set()
        self._semaphore = asyncio.Semaphore(max_concurrent_tasks)  # Control concurrency
        self._shutdown_event = asyncio.Event()
        self.cache = ResultCache(cache_size)
        self.is_processing = False
        logger.info(f"AsyncProcessor initialized: max_concurrent_tasks={max_concurrent_tasks} (NO SKIPS MODE)")

    async def _process_single_item_safe(
        self,
        item: Any,
        rule_based_engine: Any,
        original_index: int,
    ) -> TaskResult:
        """100% safe single-item processing that never skips—wrapped in semaphore for concurrency."""
        start_time = time.time()
        task_id = str(id(item))
        
        async with self._semaphore:  # Respect concurrency limits
            try:
                # Use rule-based engine to improve the content (always processes this item)
                if hasattr(item, 'masked_content') and item.masked_content:
                    # Use rule-based engine to process the content
                    processing_result = rule_based_engine._apply_rules_to_text(
                        item.masked_content, 
                        {}  # Default editing profile
                    )
                    processing_time = time.time() - start_time
                    
                    if processing_result and processing_result.get('revised_text'):
                        logger.info(f"Successfully processed item {original_index} (task {task_id})")
                        return TaskResult(
                            task_id=task_id,
                            original_index=original_index,
                            success=True,
                            revised_content=processing_result['revised_text'].strip(),
                            processing_time=processing_time
                        )
                
                # If we get here, processing failed (never skips, marks as failed)
                logger.error(f"Failed to process item {original_index} (task {task_id})")
                return TaskResult(
                    task_id=task_id,
                    original_index=original_index,
                    success=False,
                    error="Failed to generate refined content",
                    processing_time=processing_time
                )
                
            except Exception as e:
                logger.error(f"Exception processing item {original_index} (task {task_id}): {e}")
                return TaskResult(
                    task_id=task_id,
                    original_index=original_index,
                    success=False,
                    error=str(e),
                    processing_time=time.time() - start_time
                )
    
    def _create_refinement_prompt(self, content: str, paragraph_type: str) -> str:
        """Create appropriate refinement prompt based on paragraph type."""
        base_prompt = """Rewrite the following text to improve its natural flow and clarity while preserving all original meaning, facts, and placeholders. Do not add any new information or change the core message.

Text to rewrite:
{content}

Rewritten version:"""
        
        # Add specific instructions based on paragraph type
        type_specific = {
            "academic": " Maintain formal academic tone. This is scholarly content.",
            "technical": " Preserve all technical accuracy and terminology. This is technical content.",
            "literature_review": " Maintain critical analysis tone while improving flow.",
            "methodology": " Keep procedural clarity intact. This describes research methods.",
            "results": "Preserve all findings and data interpretation exactly.",
            "discussion": "Maintain the argumentative and interpretive nature.",
            "ordinary_prose": "Improve natural conversational flow while keeping the original voice."
        }
        
        # Combine prompts
        full_prompt = base_prompt.format(content=content)
        if paragraph_type in type_specific:
            full_prompt = full_prompt.replace("Rewritten version:", f"{type_specific[paragraph_type]}\n\nRewritten version:")
        
        return full_prompt
    
    async def process_batch(
        self,
        job_id: str,
        items: List[Any],
        rule_based_engine: Any,
        progress_callback: Optional[Callable[[int, int], None]] = None,
    ) -> List[TaskResult]:
        """
        Process ALL items—100% of paragraphs are processed, never skipped.
        Uses high concurrency to maintain speed while guaranteeing no items are missed.
        """
        # Create job entry
        job = Job(
            job_id=job_id,
            items=items,
            progress_callback=progress_callback
        )
        self._jobs[job_id] = job
        self.is_processing = True
        
        completed_count = 0
        failed_count = 0
        all_results: List[TaskResult] = []
        
        try:
            logger.info(f"Starting job {job_id} with {len(items)} items - ALL will be processed")
            
            # Create tasks for EVERY item (no batching = no skips)
            all_tasks = []
            for idx, item in enumerate(items):
                original_idx = idx  # Track original position 100% accurately
                task = asyncio.create_task(
                    self._process_single_item_safe(item, rule_based_engine, original_idx)
                )
                all_tasks.append(task)
                self._tasks.add(task)
                
                # Clean up task when done
                def task_done(t):
                    self._tasks.discard(t)
                task.add_done_callback(task_done)
            
            # Wait for ALL tasks to complete (every item is processed)
            all_task_results = await asyncio.gather(*all_tasks, return_exceptions=True)
            
            # Process results
            for result in all_task_results:
                if isinstance(result, TaskResult):
                    all_results.append(result)
                    if result.success:
                        completed_count += 1
                        logger.info(f"Item {result.original_index} completed successfully")
                    else:
                        failed_count += 1
                        logger.error(f"Item {result.original_index} failed: {result.error}")
                    
                    # Update job results
                    job.results.append(result)
                    
                    # Call progress callback
                    if progress_callback:
                        progress_callback(completed_count, failed_count)
            
            # Sort results back to original order to maintain document structure
            all_results.sort(key=lambda x: x.original_index)
            
            # Mark job as completed
            job.completed = True
            logger.info(f"Job {job_id} completed: {completed_count} successful, {failed_count} failed (ALL items processed)")
            
        except Exception as e:
            logger.error(f"Job {job_id} failed with error: {e}")
            job.completed = False
            raise
        finally:
            # Clean up
            if job_id in self._jobs:
                del self._jobs[job_id]
            # Update processing state
            if len(self._jobs) == 0:
                self.is_processing = False
        
        return all_results
    
    def cancel_job(self, job_id: str) -> bool:
        """Cancel a specific job by ID."""
        if job_id in self._jobs:
            self._jobs[job_id].cancelled = True
            logger.info(f"Cancelled job: {job_id}")
            return True
        return False
    
    def cancel(self):
        """Cancel all ongoing processing jobs."""
        self._shutdown_event.set()
        # Cancel all running tasks
        for task in self._tasks:
            if not task.done():
                task.cancel()
        # Clear all jobs
        self._jobs.clear()
        self.is_processing = False
    
    def get_job_status(self, job_id: str) -> Optional[Any]:
        """Get current status of a specific job."""
        if job_id not in self._jobs:
            return None
            
        job = self._jobs[job_id]
        elapsed = time.time() - job.created_time
        
        completed = len([r for r in job.results if r.success])
        failed = len([r for r in job.results if not r.success])
        total = len(job.items)
        
        from dataclasses import dataclass, field
        @dataclass
        class JobStatus:
            job_id: str
            total_items: int
            completed_items: int
            failed_items: int
            elapsed_seconds: float
            is_completed: bool
            is_cancelled: bool
            results: List[TaskResult] = field(default_factory=list)
        
        return JobStatus(
            job_id=job_id,
            total_items=total,
            completed_items=completed,
            failed_items=failed,
            elapsed_seconds=elapsed,
            is_completed=job.completed,
            is_cancelled=job.cancelled,
            results=job.results.copy()
        )