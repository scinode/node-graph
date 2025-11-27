def task_deletion_hook(self, task):
    """Hook for task deletion.

    Args:
        task (Task): a task to be deleted.
    """
    # remove all links to the task
    link_index = []
    for index, link in enumerate(self.parent.links):
        if link.from_task.name == task.name or link.to_task.name == task.name:
            link_index.append(index)
    del self.parent.links[link_index]


def test_from_dict(ng_decorator):
    """Export Graph to dict."""
    ng = ng_decorator
    assert len(ng.links) == 3
    ng.tasks.post_deletion_hooks = [task_deletion_hook]
    ng.delete_tasks("add2")
    assert len(ng.links) == 1
